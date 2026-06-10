"""インタビューの組み込み質問フレーム（Act 2）。

jibun.starter.md の節（§2 自己理解 / §3 パターン / §5 AI へ / §6 反証可能性）に
対応させた宣言データ。AI 不要・egress ゼロで完走できるのが原則で、
claude による適応的な追い質問はこのフレームの「後」に任意で足される。

resume は id で照合するので、質問の追加・並べ替えをしても回答済みは保たれる。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Question:
    id: str        # 安定 slug（resume の照合キー）
    section: str   # 対応する jibun.starter.md の節
    text: str


QUESTIONS: tuple[Question, ...] = (
    Question("now-activities", "§1/§2",
             "いま定期的にやっている活動・プロジェクトを教えてください（仕事・趣味・習慣、なんでも）。"),
    Question("time-use", "§2",
             "平日と休日、それぞれ時間を何にどれくらい使っていますか？ざっくりで OK です。"),
    Question("recent-focus", "§2",
             "ここ 1 か月でいちばん時間と気持ちを使っていることは何ですか？"),
    Question("recurring-patterns", "§3",
             "「また同じことをしているな」と自分で感じる行動パターンはありますか？"),
    Question("fun-vs-drain", "§2",
             "やっていて楽しいこと、逆にやると消耗することは何ですか？"),
    Question("procrastination", "§3",
             "先延ばしにしがちなこと、逆に過集中してしまうことはありますか？"),
    Question("struggles", "§2",
             "いま困っていること・引っかかっていることはありますか？"),
    Question("wanted-help", "§2/§5b",
             "誰か（または AI）に助けてほしいことと、逆に口出しされたくない領域を教えてください。"),
    Question("values", "§2/§5a",
             "物事を決めるときの判断基準や、大事にしている価値観は何ですか？"),
    Question("motivation", "§5a",
             "やる気が出るのはどんな条件のときですか？逆に萎えるのは？"),
    Question("ai-behavior", "§5b",
             "AI アシスタントにはどう振る舞ってほしいですか？（口調・距離感・提案の強さなど）"),
    Question("ai-donts", "§5b/§5e",
             "AI にされると嫌なこと、踏み込んでほしくない話題はありますか？"),
    Question("triggers", "§5d",
             "調子が上がるきっかけ・下がるきっかけ（追い風と向かい風）を教えてください。"),
    Question("self-doubt", "§6",
             "自分の自己認識のなかで「実はあやしいかも」と思っている点はありますか？"),
    Question("outside-view", "§6",
             "他人からの指摘で意外だったこと・思わず反発したことはありますか？"),
)
