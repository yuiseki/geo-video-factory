"""Add spoken bridges and reusable geographic camera moves to v0.1.5."""
# Applied once, turning the previous version of its input into the next; those versions are in git history.
import copy,json
from pathlib import Path
import sys
import build_story

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'packages' / 'pipeline'))
from video.shot_effects import geographic_transition
ROOT=Path(__file__).resolve().parent
source=build_story.SOURCE
backup=ROOT/'shots/dotonbori-script.md'
if not backup.exists(): backup.write_text(source.read_text())
original=backup.read_text()
base=json.loads((ROOT/'shots/dotonbori.json').read_text())
turns=build_story.parse_dialogue(original)
sections=[]
for turn in turns:
 sections.extend([turn['section']]*len(build_story.split_text(turn['text'])))
assert len(sections)==len(base['shots'])
# Every added utterance fits one shot and anticipates the following chapter.
bridges={
0:[('a','まずは、道頓堀の川辺から見ていくのだ。')],
1:[('a','ところで、隅田川でも娯楽が栄えていたと聞いたことがあるのだ。'),('b','そうね。次は江戸・東京の水辺の文化を見ていきましょう。')],
2:[('a','その近くの柳橋では、水辺の文化はどう変わったのだ？')],
3:[('b','今度は、川そのものが見えなくなった新橋へ向かいましょう。')],
4:[('a','川の記憶をたどったところで、もう一度、大阪に戻るのだ。'),('b','道頓堀から南港へ。今度は、未来を思わせる名前を訪ねましょう。')],
5:[('b','その電車が向かう先には、どんな未来が描かれていたのかしら。')],
6:[('a','それじゃあ、道頓堀と南港を並べて、二つの街を見てみるのだ。')],
7:[('b','最後に、この一日の発見を振り返ってみましょう。')],
}
for x in bridges.values():
 for _,t in x: assert len(build_story.split_text(t))==1,(t,build_story.split_text(t))
# Where the voice begins and ends; the longer moves deliberately rise, travel, then descend.
D=[135.50115,34.66881]; R=[139.78746,35.69521]; RB=[139.7888628,35.6943052]; Y=[139.7874728,35.6952154]; S=[139.7617,35.6666]; C=[135.4125,34.6427]; O=[135.457,34.654]
wide=[137.65,35.2]
def cam(center,zoom,pitch=25,bearing=0,t=None):
 d={'center':center,'zoom':zoom,'pitch':pitch,'bearing':bearing}
 if t is not None: d={'t':t,**d}
 return d
def key_move(points): return [cam(c,z,p,b,t) for t,c,z,p,b in points]
def label(name,at): return {'type':'label','text':name,'at':at,'style':'tag','show':[0,1]}
def shot(section,j,voice,text):
 loc={0:D,1:D,2:R,3:Y,4:S,5:C,6:C,7:O}[section]
 s={'from':cam(loc,14.5),'to':cam(loc,14.2,30,5),'lines':[{'voice':voice,'text':text,'speech':build_story.speech_text(text).replace('隅田川','すみだがわ'),'face':'normal' if voice=='a' else 'point'}], 'overlays':[], 'transition':True}
 if section==0: s['overlays']=[label('道頓堀川',D)]
 if section==1 and j==0:
  s['from']=cam(D,14.5); s['to']=cam(D,8.1,15); s['overlays']=[label('道頓堀川',D)]
 if section==1 and j==1:
  s['keys']=geographic_transition(D,R,midpoint=wide)
  s['overlays']=[label('道頓堀川',D),label('隅田川・両国',R)]
 if section==2:
  s['from']=cam(RB,14.5,25); s['to']=cam(Y,14.8,30,10); s['overlays']=[label('両国橋',RB),label('柳橋',Y)]
 if section==3:
  s['keys']=key_move([(0,Y,14.4,25,0),(.4,[139.776,35.682],11.7,12,0),(.7,[139.776,35.682],11.7,12,0),(1,S,14,25,0)])
  s['overlays']=[label('柳橋',Y),label('新橋・汐留川跡',S)]
 if section==4 and j==0:
  s['from']=cam(S,14.5,25); s['to']=cam(S,8.1,15); s['overlays']=[label('新橋',S)]
 if section==4 and j==1:
  s['keys']=geographic_transition(S,C,end_zoom=13.3,hold=(.27,.6),midpoint=wide)
  s['overlays']=[label('東京・新橋',S),label('大阪南港',C)]
 if section==5: s['from']=cam(C,14.7,25); s['to']=cam(C,13,30,10); s['overlays']=[label('コスモスクエア駅',C),label('大阪南港',C)]
 if section==6: s['from']=cam(C,14.5,25); s['to']=cam(O,11.3,15); s['overlays']=[label('コスモスクエア',C),label('道頓堀',D)]
 if section==7: s['from']=cam(O,11.5,20); s['to']=cam(O,11.2,15); s['overlays']=[label('道頓堀',D),label('コスモスクエア',C)]
 return s
new=[]
for i,(section,s) in enumerate(zip(sections,base['shots'])):
 new.append(s)
 if i+1==len(sections) or sections[i+1]!=section:
  for j,(voice,text) in enumerate(bridges.get(section,[])): new.append(shot(section,j,voice,text))
base['shots']=new
# Replace redundant first question after the newly added introduction.
old='江戸にも、水辺の娯楽街はあったのだ？'; newtext='江戸では、どんな人たちが集まっていたのだ？'
for s in base['shots']:
 for line in s.get('lines',[]):
  if line['text']==old: line['text']=newtext; line['speech']=build_story.speech_text(newtext)
original=original.replace(old,newtext)
for section, lines in bridges.items():
 marker='【場面'+str(section+1) if section<7 else '【結び'
 pos=original.index(marker)
 insertion=''.join('**'+('ずんだもん' if voice=='a' else '四国めたん')+'：** '+text+'\n\n' for voice,text in lines)
 original=original[:pos]+insertion+original[pos:]
source.write_text(original)
(ROOT/'shots/dotonbori.json').write_text(json.dumps(base,ensure_ascii=False,indent=2)+'\n')
print('wrote',len(base['shots']),'shots')
