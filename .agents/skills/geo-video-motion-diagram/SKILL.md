---
name: geo-video-motion-diagram
description: 地理・歴史・土木解説動画における「動く図（モーションダイアグラム）」を設計・実装・検品する。プレート衝突・熱水循環・インフラ構造・因果フローなどの模式図や分解図を、静止画ではなく時間軸に沿った動きで表現したいときに使う。
---

# 地理動画の「動く図」設計（Motion Diagram）

静止画の図解に情報を詰め込むのではなく、**時間軸を使って因果・移動・循環・構造の順序を 1 つずつ見せる「動く図」**を設計・実装するためのスキル。

構図・文字造形・3層密度・検品の基本基準は `geo-video-art-direction`、計器・警戒状態遷移の文法は `geo-video-console-layout`、現行レンダラーの標準オーバーレイ仕様は `geo-video-renderer` を参照する。

## 設計の 4 原則

1. **1 つの動く図で 1 つのメッセージ**: 複数の因果（例：「プレートの北上衝突」と「地下の熱水循環」）を 1 枚の図に詰め込まず、ショットを分けてそれぞれを主役にする。
2. **Intent First（目的のない動きを禁止）**: すべての動きは「①視線誘導」「②階層の提示」「③意味・変化の伝達」「④余韻と緩急」のいずれかに紐づける。目的を言語化できない常時回転・明滅・浮遊は置かない。
3. **静止を基準に因果の順で動かす**: 一斉に全要素を動かさず、「舞台・基準線の提示 → 原因の移動・伸長 → 結果の出現・強調」の順に時間差（Stagger: 0.1〜0.2 秒）をつけて展開する。
4. **決定論的タイムラインで実装する**: `packages/renderer/` は 1 フレームずつ時刻 `t` を進めて書き出すため、CSS `transition` / `@keyframes`・`requestAnimationFrame`・`setTimeout`・`Math.random()` は使わない。すべての視覚状態を時刻 `t` の純粋関数で計算する。

## 読む資料

- モーショングラフィックスの原則・イージング・文字組： [references/motion-grammar.md](references/motion-grammar.md)
- 決定論的アニメーション実装規約（時刻 `t` 駆動・シーク可能タイムライン・解析解スプリング）： [references/deterministic-engine.md](references/deterministic-engine.md)
- AI エージェント向け決定論違反アンチパターン集と修正例： [references/agent-motion-antipatterns.md](references/agent-motion-antipatterns.md)
- 動く図の型と現行レンダラーとの接続（標準オーバーレイ vs 事前生成）： [references/diagram-patterns.md](references/diagram-patterns.md)

## 完了前の確認

- 1 つの動く図が 1 つのメッセージ・因果に絞られているか。
- すべてのアニメーション要素について「何の物理・統計・因果変化を表す動きか」を言語化できるか。
- CSS アニメや実時間タイマーに依存せず、任意の `--fps` で同じ時刻 `t` に同じフレームが再現されるか。
- `tabular-nums`・文節折り返し・H.264 圧縮耐性（過度なグローや常時フリッカーの回避）が守られているか。
- 静止画の1コマだけでなく、通常速度の連続動画で緩急・可読性・字幕や立ち絵との非干渉を確認したか。
