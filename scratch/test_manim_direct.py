from manim import *

class AgentEchoScene(Scene):
    def construct(self):
        # 1. Title
        title = Text("Agent Echo Testing", color=BLUE_C, font_size=40)
        self.play(Write(title))
        self.wait(1)
        self.play(title.animate.to_edge(UP))

        # 2. State representation (representing our FSM / pipeline concepts)
        box1 = RoundedRectangle(corner_radius=0.15, width=2.5, height=1.0).set_fill(BLUE_E, opacity=0.3).set_stroke(BLUE_C)
        label1 = Text("Source Code", font_size=18, color=WHITE)
        state1 = VGroup(box1, label1)

        box2 = RoundedRectangle(corner_radius=0.15, width=2.5, height=1.0).set_fill(GREEN_E, opacity=0.3).set_stroke(GREEN)
        label2 = Text("Manim Animation", font_size=18, color=WHITE)
        state2 = VGroup(box2, label2).next_to(state1, RIGHT, buff=2.0)

        arrow = Arrow(state1.get_right(), state2.get_left(), color=TEAL, buff=0.1)

        self.play(FadeIn(state1, shift=RIGHT))
        self.play(GrowArrow(arrow))
        self.play(FadeIn(state2, shift=RIGHT))
        self.wait(1)

        # Highlight transition
        dot = Dot(color=YELLOW).move_to(state1)
        self.play(FadeIn(dot))
        self.play(dot.animate.move_to(state2), run_time=1.0)
        self.play(state2[0].animate.set_fill(GREEN_E, opacity=0.7), run_time=0.4)
        self.play(FadeOut(dot))
        
        self.wait(2)
