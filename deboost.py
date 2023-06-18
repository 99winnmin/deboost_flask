import tensorflow as tf
import pandas as pd
from json.encoder import INFINITY
import json
from collections import OrderedDict
import pandas as pd

def pre_processing(json_list, nick_name):
    selected_data =["allInPings","assistMePings","assists","baitPings","baronKills","basicPings",\
        "bountyLevel","champExperience","champLevel","championId","commandPings","consumablesPurchased",\
        "damageDealtToBuildings","damageDealtToObjectives","damageDealtToTurrets",\
        "damageSelfMitigated","dangerPings","deaths","detectorWardsPlaced","doubleKills",\
        "dragonKills","enemyMissingPings","enemyVisionPings","getBackPings","goldEarned",\
        "goldSpent","holdPings","inhibitorKills","inhibitorTakedowns","inhibitorsLost",\
        "itemsPurchased","killingSprees","kills","largestMultiKill","longestTimeSpentLiving",\
        "magicDamageDealt","magicDamageDealtToChampions","magicDamageTaken","needVisionPings",\
        "neutralMinionsKilled","objectivesStolen","objectivesStolenAssists","onMyWayPings",\
        "pentaKills","physicalDamageDealt","physicalDamageDealtToChampions","physicalDamageTaken",\
        "pushPings","quadraKills","summonerLevel","totalDamageDealt","totalDamageDealtToChampions",\
        "totalDamageTaken","totalHeal","totalMinionsKilled","totalTimeCCDealt","totalTimeSpentDead",\
        "tripleKills","turretKills","turretTakedowns","turretsLost","visionClearedPings",\
        "visionScore","visionWardsBoughtInGame","wardsKilled","wardsPlaced"]
    output=pd.DataFrame()
    for i in json_list:
        summoner_index= None
        gameDurationMinute=i["info"]["gameDuration"]/60
        cur_json = i["info"]["participants"]
        for index,j in enumerate(cur_json):
            if j["summonerName"]==nick_name:
                summoner_index=index
        summoner_data=cur_json[summoner_index]
        temp={}
        if summoner_data["win"]==True:
            temp["win"]=1
        else:
            temp["win"]=0
        if(summoner_data["teamPosition"]=="TOP"):
            temp["line"]=0
        if(summoner_data["teamPosition"]=="JUNGLE"):
            temp["line"]=1
        if(summoner_data["teamPosition"]=="MIDDLE"):
            temp["line"]=2
        if(summoner_data["teamPosition"]=="BOTTOM"):
            temp["line"]=3
        if(summoner_data["teamPosition"]=="UTILITY"):
            temp["line"]=4
        for j in selected_data:
            temp[j]=summoner_data[j]/gameDurationMinute
        test=[]
        test.append(temp)
        refDataFrame=pd.DataFrame(test)
        output=pd.concat([output, refDataFrame],axis=1)
    print(output)
    return output

def pred(x):
  path_to_model = 'final.ckpt'
  new_model = tf.keras.models.load_model(path_to_model)
  # x = x.to_numpy()
  # print(x.shape)
  # x = x.reshape(1, *x.shape)
  return new_model.predict(x)

def main(json_array, nick_name):
  x = pre_processing(json_array, nick_name)
  probability = pred(x)[0]
  return probability