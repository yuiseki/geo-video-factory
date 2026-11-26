"""Write v0.1.7 description with timestamps from the final chapter assembly."""
import json
from pathlib import Path
root=Path(__file__).resolve().parent
out=root/'out/v0.1.7-r2'
desc=(root/'out/v0.1.5/description.v0.1.5.txt').read_text()
chapters=json.loads((out/'chapters.json').read_text())
def stamp(n):
 s=int(n)
 return f'{s//60}:{s%60:02d}'
toc='【目次】\n'+'\n'.join(stamp(ch['start'])+' '+ch['title'] for ch in chapters)+'\n\n'
start=desc.index('【目次】\n'); end=desc.index('※写真は',start)
desc=desc[:start]+toc+desc[end:]
desc+='\n章間のカメラ移動を緩やかにし、コスモスクエア駅と大阪南港のラベルの重なりを調整しました。\n'
(out/'description.v0.1.7.txt').write_text(desc)
print(toc)
