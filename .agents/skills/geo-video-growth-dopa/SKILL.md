---
name: geo-video-growth-dopa
description: 長尺動画の導入（冒頭30秒）やショート動画において、視聴者の期待と報酬を時間軸上に配置し、離脱を防ぎつつ理解と満足度を高める編集・構成を設計する。「冒頭の離脱を減らしたい」「ショート動画向けに構成したい」「ドパ系・テンポのよい導入を作りたい」「視聴維持率を改善・検証したい」のときに使う。
---

# 期待と報酬の映像設計（グロース・ドパ）

「ドパ」を**刺激の量を最大化すること**ではなく、**「視聴者の期待と報酬を時間軸上に配置し、注意の獲得・維持と知的満足を両立する設計」**として扱う。

- **長尺動画の導入 = 入口の設計**: 冒頭 0〜30 秒で価値や結論の一部を先出しし、本編を見る理由を作る。[references/long-form-intro.md](references/long-form-intro.md)
- **ショート動画 = 体験の密度設計**: 冒頭 1〜3 秒でフックを作り、短い間隔で発見や小報酬を重ね、動画内で体験を完結させる。[references/short-form.md](references/short-form.md)

## 手順

1. **形式と方針を決める**: 長尺の導入かショート動画かを確認する。静かな紀行や正確さ最優先の説明など、高刺激導入を避けるべき題材かも判断する。[references/long-form-intro.md](references/long-form-intro.md)
2. **4つの役割を時間軸に置く**: すべてのカット・演出を「注意の獲得」「期待の形成」「報酬の提供」「注意の再獲得」のいずれかに割り当てる。[references/techniques-and-constraints.md](references/techniques-and-constraints.md)
3. **過剰複雑化を避けつつ演出を組む**: 短いショットと単純な画面構成は注意の同期を高める一方、視覚的複雑さの増やしすぎは理解を妨げる。強調の前後には必ず静かな間（ダイナミックレンジ）を置く。[references/short-form.md](references/short-form.md)
4. **地理動画の実装へ落とす**: `rise`、`focus`、`counter`、`line` 描画、カメラの視線誘導・緩急、SE など、既存のレンダラー機能で実装できる形へ変換する。[references/techniques-and-constraints.md](references/techniques-and-constraints.md)
5. **安全性と検証計画を添える**: 光過敏対策（WCAG 2.2）を確認し、再生回数だけでなく継続視聴（Engaged views）や理解度で効果を検証する。[references/experiment-and-safety.md](references/experiment-and-safety.md)

## 守ること

- 「ドパ」は編集上の比喩であり、神経科学的な計測単位（ドーパミン分泌量や依存症の診断）として語らない。
- 後半で回収できない成果や結論を冒頭で予告しない（釣り・信頼毀損の禁止）。
- すべての場面を強調しない。強調する瞬間を際立たせるために、相対的に落ち着いた区間を残す。
- 1秒間に3回を超える閃光や過度な画面振動・音量急変を避け、字幕の可読性を保つ。
