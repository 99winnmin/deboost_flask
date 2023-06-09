import os
import time
import torch
import argparse
import torch.nn as nn
import torchvision.transforms as tfs
from torch.utils.data import DataLoader
from timm.models.layers import trunc_normal_
from torchvision.datasets.cifar import CIFAR10
from torch.utils.data import TensorDataset
import numpy as np

class EmbeddingLayer(nn.Module):
    def __init__(self, in_chans, embed_dim, img_size, patch_size):
        super().__init__()
        self.num_tokens = in_chans
        self.embed_dim = embed_dim
        self.project = nn.Conv2d(in_chans, embed_dim, kernel_size=patch_size, stride=patch_size)

        self.cls_token = nn.Parameter(torch.zeros(1, 1, embed_dim))
        self.num_tokens += 1
        self.pos_embed = nn.Parameter(torch.zeros(1, 11, self.embed_dim))

        # init cls token and pos_embed -> refer timm vision transformer
        # https://github.com/rwightman/pytorch-image-models/blob/master/timm/models/vision_transformer.py#L391
        nn.init.normal_(self.cls_token, std=1e-6)
        trunc_normal_(self.pos_embed, std=.02)

    def forward(self, x):
        B, C, H, W = x.shape
        x = x.view(B, 1, 100, 10) # [:,1,100,10]
        # x = x.unsqueeze(1)

        # x = x[:,:-1,:,:]
        # x1 = torch.cat([x[:,0,:,:],x[:,1,:,:],x[:,2,:,:]], dim=2)
        # x2 = torch.cat([x[:,3,:,:],x[:,4,:,:],x[:,5,:,:]], dim=2)
        # x3 = torch.cat([x[:,6,:,:],x[:,7,:,:],x[:,8,:,:]], dim=2)

        # x = torch.cat([x1,x2,x3],dim=1)

        # x = x.unsqueeze(1)
        # print('x.shape', x.shape)
        embedding = self.project(x)
        # print('embedding.shape', embedding.shape)
        z = embedding.view(B, self.embed_dim, -1).permute(0, 2, 1)  # BCHW -> BNC
        # print(z.shape)
        # concat cls token
        cls_tokens = self.cls_token.expand(B, -1, -1)
        z = torch.cat([cls_tokens, z], dim=1)

        # add position embedding
        z = z + self.pos_embed
        return z


class MSA(nn.Module):
    def __init__(self, dim=192, num_heads=4, qkv_bias=False, attn_drop=0., proj_drop=0.):
        super().__init__()
        assert dim % num_heads == 0, 'dim should be divisible by num_heads'
        self.num_heads = num_heads
        head_dim = dim // num_heads
        self.scale = head_dim ** -0.5

        self.qkv = nn.Linear(dim, dim * 3, bias=qkv_bias)
        self.attn_drop = nn.Dropout(attn_drop)
        self.proj = nn.Linear(dim, dim)
        self.proj_drop = nn.Dropout(proj_drop)

    def forward(self, x):
        B, N, C = x.shape
        qkv = self.qkv(x).reshape(B, N, 3, self.num_heads, C // self.num_heads).permute(2, 0, 3, 1, 4)
        q, k, v = qkv.unbind(0)

        attn = (q @ k.transpose(-2, -1)) * self.scale

        attn = attn.softmax(dim=-1)
        attn = self.attn_drop(attn)

        x = (attn @ v).transpose(1, 2).reshape(B, N, C)
        x = self.proj(x)
        x = self.proj_drop(x)
        return x


class MLP(nn.Module):
    def __init__(self, in_features, hidden_features, act_layer=nn.GELU, bias=True, drop=0.):
        super().__init__()
        out_features = in_features

        self.fc1 = nn.Linear(in_features, hidden_features, bias=bias)
        self.act = act_layer()
        self.drop1 = nn.Dropout(drop)
        self.fc2 = nn.Linear(hidden_features, out_features, bias=bias)
        self.drop2 = nn.Dropout(drop)

    def forward(self, x):
        x = self.fc1(x)
        x = self.act(x)
        x = self.drop1(x)
        x = self.fc2(x)
        x = self.drop2(x)
        return x


class Block(nn.Module):

    def __init__(self, dim, num_heads, mlp_ratio=4., qkv_bias=False,
                 drop=0., attn_drop=0., act_layer=nn.GELU, norm_layer=nn.LayerNorm,
                 ):
        super().__init__()
        self.norm1 = norm_layer(dim)
        self.norm2 = norm_layer(dim)
        self.attn = MSA(dim, num_heads=num_heads, qkv_bias=qkv_bias, attn_drop=attn_drop, proj_drop=drop)
        self.mlp = MLP(in_features=dim, hidden_features=int(dim * mlp_ratio), act_layer=act_layer, drop=drop)

    def forward(self, x):
        x = x + self.attn(self.norm1(x))
        x = x + self.mlp(self.norm2(x))
        return x


class ViT(nn.Module):
    def __init__(self, img_size=10, patch_size=10, in_chans=1, num_classes=9, embed_dim=192, depth=4,
                 num_heads=4, mlp_ratio=2., qkv_bias=False, drop_rate=0., attn_drop_rate=0.):
        super().__init__()
        self.num_classes = num_classes
        self.num_features = self.embed_dim = embed_dim  # num_features for consistency with other models
        norm_layer = nn.LayerNorm
        act_layer = nn.GELU

        self.patch_embed = EmbeddingLayer(in_chans, embed_dim, img_size, patch_size)
        self.blocks = nn.Sequential(*[
            Block(
                dim=embed_dim, num_heads=num_heads, mlp_ratio=mlp_ratio, qkv_bias=qkv_bias, drop=drop_rate,
                attn_drop=attn_drop_rate, norm_layer=norm_layer, act_layer=act_layer)
            for i in range(depth)])

        # final norm
        self.norm = norm_layer(embed_dim)

        # Classifier head(s)
        self.head = nn.Linear(self.num_features, num_classes) if num_classes > 0 else nn.Identity()

    def forward(self, x):
        x = self.patch_embed(x)
        x = self.blocks(x)
        x = self.norm(x)
        x = self.head(x)[:, 0]
        return x

def main():
    # 1. ** argparser **
    parer = argparse.ArgumentParser()
    parer.add_argument('--epoch', type=int, default=150)
    parer.add_argument('--batch_size', type=int, default=128)
    parer.add_argument('--lr', type=float, default=0.001)
    parer.add_argument('--step_size', type=int, default=100)
    parer.add_argument('--root', type=str, default='./CIFAR10')
    parer.add_argument('--log_dir', type=str, default='./log')
    parer.add_argument('--name', type=str, default='vit_cifar10')
    parer.add_argument('--rank', type=int, default=0)
    ops = parer.parse_args()

    # 2. ** device **
    device = torch.device('cuda:{}'.format(0) if torch.cuda.is_available() else 'cpu')

    # 3. ** visdom **
    # vis = visdom.Visdom(port=8097)

    # 4. ** dataset / dataloader **
    transform_cifar = tfs.Compose([
        tfs.RandomCrop(32, padding=4),
        tfs.RandomHorizontalFlip(),
        tfs.ToTensor(),
        tfs.Normalize(mean=(0.4914, 0.4822, 0.4465),
                      std=(0.2023, 0.1994, 0.2010)),
    ])

    X_train = torch.FloatTensor(np.load('train/X_train0_9.npy'))
    y_train = torch.LongTensor(np.load('train/y_train0_9.npy'))
    # print('X_train.shape:',X_train.shape)

    train_set = TensorDataset(X_train, y_train)
    batch_size = 256
    train_loader = torch.utils.data.DataLoader(dataset=train_set,
                                            batch_size=256,
                                            shuffle=True,
                                            drop_last=True)
    X_test = torch.FloatTensor(np.load('test/X_test0_9.npy'))
    y_test = torch.FloatTensor(np.load('test/y_test0_9.npy'))

    test_set = TensorDataset(X_test, y_test)

    test_loader = DataLoader(dataset=test_set,
                             shuffle=True,
                             batch_size=256)

    # 5. ** model **
    model = ViT().to(device)

    # 6. ** criterion **
    criterion = nn.MSELoss()

    # 7. ** optimizer **
    optimizer = torch.optim.Adam(model.parameters(),
                                 lr=ops.lr,
                                 weight_decay=5e-5)

    # 8. ** scheduler **
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=ops.epoch, eta_min=1e-5)

    # 9. ** logger **
    os.makedirs(ops.log_dir, exist_ok=True)

    # 10. ** training **
    print("training...")
    for epoch in range(ops.epoch):

        model.train()
        tic = time.time()
        for idx, (img, target) in enumerate(train_loader):
            img = img.to(device)  # [N, 3, 32, 32]
            target = target.to(device)  # [N]
            # output, attn_mask = model(img, True)  # [N, 10]
            output = model(img)  # [N, 10]
            loss = criterion(output, target.float())
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            for param_group in optimizer.param_groups:
                lr = param_group['lr']

            if idx % ops.step_size == 0:
                # vis.line(X=torch.ones((1, 1)) * idx + epoch * len(train_loader),
                #          Y=torch.Tensor([loss]).unsqueeze(0),
                #          update='append',
                #          win='training_loss',
                #          opts=dict(x_label='step',
                #                    y_label='loss',
                #                    title='loss',
                #                    legend=['total_loss']))

                print('Epoch : {}\t'
                      'step : [{}/{}]\t'
                      'loss : {}\t'
                      'lr   : {}\t'
                      'time   {}\t'
                      .format(epoch,
                              idx, len(train_loader),
                              loss,
                              lr,
                              time.time() - tic))

        # save
        save_path = os.path.join(ops.log_dir, ops.name, 'saves')
        os.makedirs(save_path, exist_ok=True)

        checkpoint = {'epoch': epoch,
                      'model_state_dict': model.state_dict(),
                      'optimizer_state_dict': optimizer.state_dict(),
                      'scheduler_state_dict': scheduler.state_dict()}

        torch.save(checkpoint, os.path.join(save_path, ops.name + '.{}.pth.tar'.format(epoch)))

        # 10. ** test **
        print('Validation of epoch [{}]'.format(epoch))
        model.eval()
        correct = 0
        val_avg_loss = 0
        total = 0
        with torch.no_grad():

            for idx, (img, target) in enumerate(test_loader):
                model.eval()
                img = img.to(device)  # [N, 3, 32, 32]
                target = target.to(device)  # [N]
                output = model(img)  # [N, 10]
                loss = criterion(output, target)

                output = torch.softmax(output, dim=1)
                # first eval
                pred, idx_ = output.max(-1)
                tmp, tmp2 = target.max(-1)
                correct += torch.eq(tmp2, idx_).sum().item()
                total += target.size(0)
                val_avg_loss += loss.item()

        print('Epoch {} test : '.format(epoch))
        accuracy = correct / total
        print("accuracy : {:.4f}%".format(accuracy * 100.))

        val_avg_loss = val_avg_loss / len(test_loader)
        print("avg_loss : {:.4f}".format(val_avg_loss))

        # if vis is not None:
        #     vis.line(X=torch.ones((1, 2)) * epoch,
        #              Y=torch.Tensor([accuracy, val_avg_loss]).unsqueeze(0),
        #              update='append',
        #              win='test_loss',
        #              opts=dict(x_label='epoch',
        #                        y_label='test_',
        #                        title='test_loss',
        #                        legend=['accuracy', 'avg_loss']))
        scheduler.step()


if __name__ == '__main__':
    main()