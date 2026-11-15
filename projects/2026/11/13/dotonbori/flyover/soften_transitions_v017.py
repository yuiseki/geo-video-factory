"""Reduce geographic transition speed without changing the dialogue."""
import json
from pathlib import Path
root=Path(__file__).resolve().parent
spec=json.loads((root/'shots/dotonbori.v0.1.6.json').read_text())
durations={
 'ところで、隅田川でも娯楽が栄えていたと聞いたことがあるのだ。':8.5,
 'そうね。次は江戸・東京の水辺の文化を見ていきましょう。':11.0,
 '今度は、川そのものが見えなくなった新橋へ向かいましょう。':8.0,
 '川の記憶をたどったところで、もう一度、大阪に戻るのだ。':8.5,
 '道頓堀から南港へ。今度は、未来を思わせる名前を訪ねましょう。':11.0,
 'その電車が向かう先には、どんな未来が描かれていたのかしら。':7.0,
}
found=set()
for shot in spec['shots']:
 text=shot['lines'][0]['text']
 if shot.get('transition') and text in durations:
  shot['duration']=durations[text]
  shot['ease']='smooth'
  if text.startswith('その電車が向かう先'):
   for overlay in shot['overlays']:
    if overlay.get('text') == 'コスモスクエア駅': overlay['at'] = [135.4122147,34.6425771]
    if overlay.get('text') == '大阪南港': overlay['at'] = [135.426,34.630]
  found.add(text)
assert found==durations.keys()
(root/'shots/dotonbori.v0.1.7.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2)+'\n')
print('adjusted',len(found),'shots')
