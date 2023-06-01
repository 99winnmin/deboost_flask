import torch
from deboost0 import ViT
import numpy as np
"""
checkpoint_path: 모델의 경로

실행 전
  아마 다음 세 가지 install 해야될거임
  pip install timm
  pip intall torch
  pip intall numpy
  더 하라고 하면 하고

  준 세개를 한 폴더 안에 넣으면 됨

실행 방법
  서버에서 import deboost_runner 한 다음에
  deboost_runner.run(여기에 한 게임의 json 파일)을 실행

실행 결과
  길이가 9인 배열이 반환
  0번부터 챌린저 -> 그마 -> 마스터 -> ... -> 아이언
"""
checkpoint_path = 'model.pth.tar'

if checkpoint_path == 'model.pth.tar':
  print('checkpoint_path 경로 바꿔라')
  quit()

position_encode = {'TOP':0,'MIDDLE':1,'JUNGLE':2,'BOTTOM':3,'UTILITY':4}
def pre_process(match_data):
    deletion = ['summonerName', 'individualPosition','lane','puuid','profileIcon','riotIdName','riotIdTagline','role','summonerId','championName','perks','challenges']
    participants = match_data['info']['participants']
    data = []
    for part in participants:
        if len(part.keys()) < 121:
            return None
        for d in deletion:
            del part[d]
        if part['teamPosition'] =='':
            continue
        part['teamPosition'] = position_encode[part['teamPosition']]
        one_data = part.values()
        one_data = list(one_data)
        one_data = np.array(one_data)
        one_data = one_data[:100]
        one_data = one_data.reshape((10,10))
        data.append(one_data)
    if np.array(data).shape != (10,10,10):
        return None
    return data

def load_model():
  checkpoint = torch.load(checkpoint_path)
  model = ViT()
  model.load_state_dict(checkpoint['model_state_dict'])
  return model

def run(json_obj):
  model = load_model()
  X = pre_process(json_obj)
  X = torch.FloatTensor(X)
  X = X.unsqueeze(0)
  pred = model(X)
  n = torch.nn.Softmax(dim=1)
  pred = n(pred)
  return pred.tolist()