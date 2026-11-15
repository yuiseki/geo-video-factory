# Insert a ~20 s digest (cold open) before the title shot. Run once.
import json
p='shots/moyashi.json'; d=json.load(open(p))
if d['shots'][0].get('digest'): raise SystemExit('already has a digest')
chart=[o for s in d['shots'] for o in s['overlays'] if o['type']=='chart'][0]
fast=dict(chart); fast['show']=[0.05,1]; fast['drawSec']=1.6
IR='イラスト：いらすとや'
digest=[
 {"digest":True,"from":{"center":[139.752,35.700],"zoom":14.2,"pitch":64,"bearing":40},"to":{"center":[139.754,35.702],"zoom":14.8,"pitch":66,"bearing":55},"ease":"out",
  "lines":[{"voice":"a","text":"ヤサイマシマシが、できない！？"}],
  "overlays":[{"type":"quote","source":"FNNプライムオンライン(文春オンライン掲載)","date":"2026-10-16","text":"本日“ヤサイマシマシ”できません","screen":[70,160],"width":760,"cps":40,"show":[0,1]},
              {"type":"sticker","src":"assets/irasutoya/ramen_moyashi.png","screen":[1500,380],"width":280,"credit":IR,"show":[0.1,1]}]},
 {"digest":True,"from":{"center":[56.4,26.5],"zoom":6.6,"pitch":40,"bearing":-10},"to":{"center":[56.4,26.5],"zoom":7.3,"pitch":48,"bearing":10},"ease":"out",
  "lines":[{"voice":"b","text":"8000キロ先の海峡では、船が1日3隻しか通れない。"}],
  "overlays":[{"type":"label","at":[56.4,26.5],"text":"ホルムズ海峡","style":"tag","show":[0.05,1]},
              {"type":"counter","screen":[70,160],"caption":"11月8日に通った船","value":3,"from":85,"countUp":[0.1,0.6],"unit":"隻","show":[0.05,1]}]},
 {"digest":True,"from":{"center":[139.73,35.69],"zoom":10.9,"pitch":52,"bearing":0},"to":{"center":[139.73,35.69],"zoom":11.3,"pitch":56,"bearing":10},"ease":"out",
  "lines":[{"voice":"b","text":"なのに、東京のもやしの平均価格は、ほとんど上がっていない。"}],
  "overlays":[fast]},
 {"digest":True,"from":{"center":[139.52,35.876],"zoom":12.5,"pitch":60,"bearing":345},"to":{"center":[139.52,35.879],"zoom":13.0,"pitch":63,"bearing":358},"ease":"out",
  "lines":[{"voice":"a","text":"それでも、作る会社は消えていくのだ…"}],
  "overlays":[{"type":"counter","screen":[70,160],"caption":"全国のもやし生産者 (協会のまとめ)","value":86,"from":235,"countUp":[0.05,0.7],"unit":"社","show":[0,1]},
              {"type":"sticker","src":"assets/irasutoya/building_koujou_entotsu.png","screen":[1540,400],"width":260,"credit":IR,"show":[0.1,1]}]},
 {"digest":True,"from":{"center":[100.0,30.0],"zoom":3.2,"pitch":20,"bearing":0},"to":{"center":[132.0,33.0],"zoom":4.4,"pitch":32,"bearing":0},"ease":"inOut",
  "lines":[{"voice":"b","text":"もやしの値段の裏で、いったい何が起きているのか。"}],
  "overlays":[{"type":"line","coords":[[56.4,26.4],[60.0,22.0],[80.0,6.0],[104.0,1.3],[120.0,22.0],[139.7,35.6]],"color":"#4aa3ff","width":5,"draw":[0.0,0.8]}]}
]
d['shots']=digest+d['shots']
json.dump(d,open(p,'w'),ensure_ascii=False,indent=2)
print('shots', len(d['shots']))
