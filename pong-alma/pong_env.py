# -*- coding: utf-8 -*-
"""
PONG-ALMA ENV — normalized Pong, 100% ours, pure Python stdlib.
================================================================
Field is the unit square [0,1] x [0,1].
  * Left paddle at x=0, right paddle at x=1.
  * step(aL, aR) with actions in {-1, 0, +1} (move paddle down/stay/up in y).
  * Returns ((obsL, obsR), rL, rR, done).
  * obs per side = (ball_x, ball_y, ball_vx, ball_vy, my_y)
    — MIRRORED for the right side (ball_x -> 1-ball_x, vx -> -vx) so both
    sides see the same egocentric world and one brain can play either side.
  * reward: +1 the moment your paddle HITS the ball, -1 the moment you MISS.
  * done=True on any miss (call reset() to serve again).
Deterministic: everything driven by random.Random(seed).
"""
import random


class PongEnv:
    def __init__(self, seed=0,
                 paddle_half=0.10,     # half-height of each paddle
                 paddle_speed=0.05,    # paddle dy per step
                 ball_speed=0.025,     # |vx| of the ball
                 max_vy=0.04):
        self.rng = random.Random(seed)
        self.paddle_half = paddle_half
        self.paddle_speed = paddle_speed
        self.ball_speed = ball_speed
        self.max_vy = max_vy
        self.reset()

    # ── serve / reset ────────────────────────────────────────────────
    def reset(self):
        self.yL = 0.5
        self.yR = 0.5
        self.bx = 0.5
        self.by = self.rng.uniform(0.3, 0.7)
        direction = 1 if self.rng.random() < 0.5 else -1
        self.bvx = direction * self.ball_speed
        self.bvy = self.rng.uniform(-0.02, 0.02)
        self.done = False
        return self._obs()

    # ── observations (egocentric per side) ───────────────────────────
    def _obs(self):
        obsL = (self.bx, self.by, self.bvx, self.bvy, self.yL)
        obsR = (1.0 - self.bx, self.by, -self.bvx, self.bvy, self.yR)
        return obsL, obsR

    # ── one tick ─────────────────────────────────────────────────────
    def step(self, aL, aR):
        """aL, aR in {-1, 0, +1}. Returns ((obsL, obsR), rL, rR, done)."""
        if self.done:
            raise RuntimeError("episode is done — call reset()")
        rL = 0.0
        rR = 0.0

        # paddles
        aL = -1 if aL < 0 else (1 if aL > 0 else 0)
        aR = -1 if aR < 0 else (1 if aR > 0 else 0)
        self.yL = min(1.0 - self.paddle_half,
                      max(self.paddle_half, self.yL + aL * self.paddle_speed))
        self.yR = min(1.0 - self.paddle_half,
                      max(self.paddle_half, self.yR + aR * self.paddle_speed))

        # ball
        self.bx += self.bvx
        self.by += self.bvy

        # bounce off top/bottom walls
        if self.by < 0.0:
            self.by = -self.by
            self.bvy = -self.bvy
        elif self.by > 1.0:
            self.by = 2.0 - self.by
            self.bvy = -self.bvy

        # left goal line
        if self.bx <= 0.0:
            if abs(self.by - self.yL) <= self.paddle_half:
                rL = 1.0                                    # HIT
                self.bx = -self.bx
                self.bvx = abs(self.bvx)
                # deflection depends on where on the paddle it struck
                off = (self.by - self.yL) / self.paddle_half
                self.bvy = max(-self.max_vy,
                               min(self.max_vy, self.bvy + 0.02 * off))
            else:
                rL = -1.0                                   # MISS
                self.done = True

        # right goal line
        elif self.bx >= 1.0:
            if abs(self.by - self.yR) <= self.paddle_half:
                rR = 1.0                                    # HIT
                self.bx = 2.0 - self.bx
                self.bvx = -abs(self.bvx)
                off = (self.by - self.yR) / self.paddle_half
                self.bvy = max(-self.max_vy,
                               min(self.max_vy, self.bvy + 0.02 * off))
            else:
                rR = -1.0                                   # MISS
                self.done = True

        return self._obs(), rL, rR, self.done


# ── tiny smoke demo ───────────────────────────────────────────────────
if __name__ == "__main__":
    env = PongEnv(seed=7)
    rng = random.Random(1)
    total = [0.0, 0.0]
    steps = 0
    obs = env.reset()
    for _ in range(2000):
        (o, rL, rR, done) = env.step(rng.choice((-1, 0, 1)),
                                     rng.choice((-1, 0, 1)))
        total[0] += rL
        total[1] += rR
        steps += 1
        if done:
            env.reset()
    print(f"smoke: {steps} steps, random-vs-random reward L={total[0]:+.0f} R={total[1]:+.0f}")
