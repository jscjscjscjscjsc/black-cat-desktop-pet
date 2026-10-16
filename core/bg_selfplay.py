"""Optional offline eight-seat laboratory; never imported by the pet runtime.

External HSBRSIM is loaded only from an explicit, revision-checked checkout.
This is a restricted simulator profile, NOT a current-live-game rules engine.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import random
import subprocess
import sys
import time

ENGINE_REVISION = "4e0525a198352557ef816bd3a53566d6ffd4c164"
PROFILE = "hsrl2-neutral-minion-lab-v1"
KINDS = ("END", "BUY", "SELL", "PLAY", "REFRESH", "UPGRADE")
FEATURE_DIM = 28


def load_engine(path):
    root = Path(path).resolve()
    revision = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True, timeout=10
    ).strip()
    if revision != ENGINE_REVISION:
        raise ValueError(f"Engine revision mismatch: expected {ENGINE_REVISION}, got {revision}")
    changes = subprocess.check_output(
        ["git", "-C", str(root), "diff", "--name-only", "HEAD", "--", "hsrl2", "data"],
        text=True, timeout=10
    ).strip()
    if changes:
        raise ValueError("Engine/data have tracked local changes; refusing an unrecorded rules variant")
    sys.path.insert(0, str(root))
    import hsrl2
    if Path(hsrl2.__file__).resolve().parent != root / "hsrl2":
        raise ValueError("A different hsrl2 installation is already imported")
    from hsrl2.db import CardDB
    from hsrl2.game import Game
    from hsrl2.hero import Hero
    from hsrl2.minion import Minion
    from hsrl2.spell import Spell
    from hsrl2.tags import GameTag
    from hsrl2.scripts import REGISTRY

    class LabDB(CardDB):
        def pool_minions(self):
            # Known missing script from upstream's strict registry audit.
            return [d for d in super().pool_minions() if d.id != "BG33_319"]

    db = LabDB.load(root / "data")
    missing = [d.id for d in db.pool_minions() if d.id not in REGISTRY and
               any(word in d.text for word in ("After", "Whenever", "Battlecry", "Deathrattle",
                                               "Avenge", "Spellcraft", "end of", "start of"))]
    if missing:
        raise ValueError(f"Unscripted effect cards in laboratory pool: {missing}")
    return dict(Game=Game, Hero=Hero, Minion=Minion, Spell=Spell, Tag=GameTag, db=db,
                revision=revision, root=root)


@dataclass(frozen=True)
class Choice:
    kind: str
    index: int = -1


def placement_from_groups(groups):
    """Last surviving group first; same-round eliminations share average rank."""
    ranks = {}
    next_rank = 1
    for group in groups:
        rank = next_rank + (len(group) - 1) / 2
        for seat in group:
            ranks[seat] = rank
        next_rank += len(group)
    if set(ranks) != set(range(8)):
        raise ValueError("Placement groups must contain each of eight seats exactly once")
    if sum(len(g) for g in groups) != 8:
        raise ValueError("Duplicate seat in placement groups")
    return [ranks[i] for i in range(8)]


def top4_credit(placements, seat):
    """Fractional top-four credit when a same-round tie crosses fourth place."""
    rank = placements[seat]
    count = placements.count(rank)
    first = rank - (count - 1) / 2
    return max(0., min(float(count), 5 - first)) / count


class Arena:
    def __init__(self, engine, *, turn_limit=45, action_limit=60, seconds=120):
        self.e = engine
        self.turn_limit = turn_limit
        self.action_limit = action_limit
        self.seconds = seconds

    def actions(self, game, hero):
        E, T = self.e, self.e["Tag"]
        actions = [Choice("END")]
        if hero.get(T.TURN_SKIPPED, False):
            return actions
        if not hero.hand_full():
            for i, card in enumerate(hero.tavern):
                cost = card.get(T.COST, 3)
                if isinstance(card, E["Minion"]) and hero.gold >= cost:
                    actions.append(Choice("BUY", i))
        actions += [Choice("SELL", i) for i in range(len(hero.board))]
        for i, card in enumerate(hero.hand):
            d = game.db.get(card.card_id)
            if card.has(T.LOCKED_IN_HAND) or (d and d.unplayable):
                continue
            if isinstance(card, E["Minion"]) and not hero.board_full():
                actions.append(Choice("PLAY", i))
            # Generated spell/target decisions are excluded from this first profile.
        if hero.gold >= 1 or hero.get(T.FREE_REFRESH_REMAINING, 0) > 0:
            actions.append(Choice("REFRESH"))
        if hero.tavern_tier < 6 and hero.gold >= max(0, hero.upgrade_cost):
            actions.append(Choice("UPGRADE"))
        return actions

    def features(self, game, hero, actions):
        T = self.e["Tag"]
        strength = lambda m: m.atk + m.health + (5 if m.has(T.DIVINE_SHIELD) else 0)
        weak = min((strength(m) for m in hero.board), default=0)
        best = max((strength(m) for m in hero.tavern if isinstance(m, self.e["Minion"])), default=0)
        state = [game.turn / 20, hero.gold / 10, (hero.health + hero.armor) / 40,
                 hero.tavern_tier / 6, hero.upgrade_cost / 10, len(hero.board) / 7,
                 len(hero.hand) / 10, sum(strength(m) for m in hero.board) / 200]
        rows = []
        for action in actions:
            card = None
            if action.kind in ("BUY", "SELL", "PLAY"):
                card = {"BUY": hero.tavern, "SELL": hero.board, "PLAY": hero.hand}[action.kind][action.index]
            values = [0.] * 14
            if card is not None:
                d = game.db.get(card.card_id)
                values = [card.atk / 30, card.health / 30,
                          getattr(card, "tech_level", 1) / 6,
                          float(card.has(T.DIVINE_SHIELD)), float(card.has(T.TAUNT)),
                          float(card.has(T.REBORN)), float(card.has(T.WINDFURY)),
                          float(card.has(T.VENOMOUS)), float(card.has(T.CLEAVE)),
                          sum(m.card_id == card.card_id for m in hero.board + hero.hand) / 3,
                          (strength(card) - weak) / 30, (best - strength(card)) / 30,
                          float(bool(d and "battlecry" in d.keywords)),
                          float(bool(d and "deathrattle" in d.keywords))]
            rows.append([float(action.kind == k) for k in KINDS] + state + values)
        assert all(len(row) == FEATURE_DIM for row in rows)
        return rows

    def heuristic(self, game, hero, actions):
        rows = self.features(game, hero, actions)
        scores = []
        for action, row in zip(actions, rows):
            stat = (row[14] + row[15]) * 30 + row[17] * 5
            if action.kind == "PLAY":
                score = 100 + stat
            elif action.kind == "BUY":
                score = (30 + stat) if len(hero.board) + len(hero.hand) < 7 else -20
            elif action.kind == "UPGRADE":
                expected = min(6, 1 + game.turn // 2)
                score = 75 if hero.tavern_tier < expected else -15
            elif action.kind == "SELL":
                score = 40 + row[25] * 30 if (len(hero.board) == 7 and hero.gold >= 2
                                                   and row[25] > .15) else -100
            elif action.kind == "REFRESH":
                score = 5 if hero.gold >= 4 else -10
            else:
                score = 0
            scores.append(score)
        return max(range(len(actions)), key=lambda i: scores[i])

    def execute(self, game, hero, action):
        if action.kind == "END":
            return
        if action.kind == "BUY":
            ok = game.buy_from_tavern(hero, hero.tavern[action.index])
        elif action.kind == "SELL":
            ok = game.sell_minion(hero, hero.board[action.index])
        elif action.kind == "PLAY":
            ok = game.play_minion(hero, hero.hand[action.index])
        elif action.kind == "UPGRADE":
            ok = game.upgrade_tavern(hero)
        elif action.kind == "REFRESH":
            game.refresh_tavern(hero)
            ok = True
        else:
            raise ValueError(action.kind)
        if not ok:
            raise RuntimeError(f"Masked legal action rejected: {action}")
        game.queue.resolve(game)
        self.resolve_choices(game)

    @staticmethod
    def resolve_choices(game):
        # Fixed, explicitly recorded helper. Target/discover policy is not learned yet.
        for _ in range(40):
            if not game.pending_choices:
                return
            choice = game.pending_choices.pop(0)
            if not choice.options:
                raise RuntimeError("Pending choice has no options")
            choice.choose(0)
            game.queue.resolve(game)
        raise RuntimeError("Pending-choice chain exceeded laboratory budget")

    def run(self, policies, seed, *, collect=False):
        if len(policies) != 8:
            raise ValueError("Exactly eight seat policies required")
        random.seed(seed)
        heroes = [self.e["Hero"](f"LAB_{i}", f"Seat{i}", armor=10) for i in range(8)]
        game = self.e["Game"](heroes.copy(), self.e["db"], seed=seed)
        game.choice_policy = "first"  # Explicit fixed helper; not learned targeting/discover.
        game.start_game()
        self.resolve_choices(game)
        started = time.monotonic()
        trajectories = [[] for _ in range(8)]
        eliminated_groups, turns, combat_phases, capped = [], [], 0, 0
        for _ in range(self.turn_limit):
            if time.monotonic() - started > self.seconds:
                raise TimeoutError("Game exceeded wall-time budget")
            for seat, hero in enumerate(heroes):
                if hero not in game.heroes or not hero.is_alive:
                    continue
                for step in range(self.action_limit):
                    actions = self.actions(game, hero)
                    rows = self.features(game, hero, actions)
                    teacher = self.heuristic(game, hero, actions)
                    selected = policies[seat](rows, teacher)
                    if not isinstance(selected, int) or not 0 <= selected < len(actions):
                        raise ValueError("Policy returned invalid candidate index")
                    if collect:
                        trajectories[seat].append(dict(x=rows, action=selected, teacher=teacher,
                                                       turn=game.turn, kind=actions[selected].kind))
                    action = actions[selected]
                    self.execute(game, hero, action)
                    if action.kind == "END":
                        break
                else:
                    capped += 1
            turn = game.turn
            before = set(game.heroes)
            game.end_recruit_phase()  # Exceptions propagate; never skip broken combat.
            self.resolve_choices(game)
            combat_phases += 1
            eliminated = [i for i, h in enumerate(heroes) if h in before and h not in game.heroes]
            if eliminated:
                eliminated_groups.append(eliminated)
            turns.append(dict(turn=turn, alive=len(game.heroes), eliminated=eliminated,
                              health=[h.health + h.armor for h in heroes]))
            if game.finished:
                break
        finished = game.finished and len(game.heroes) <= 1
        ranks = None
        if finished:
            survivor = [i for i, h in enumerate(heroes) if h in game.heroes]
            groups = ([survivor] if survivor else []) + eliminated_groups[::-1]
            ranks = placement_from_groups(groups)
        return dict(profile=PROFILE, engine_revision=self.e["revision"], seed=seed,
                    finished=finished, turns=turns, combat_phases=combat_phases,
                    placements=ranks, action_limit_hits=capped,
                    trajectories=trajectories, elapsed_seconds=round(time.monotonic()-started, 3))


def teacher_policy(rows, teacher):
    return teacher


def random_policy(rng):
    return lambda rows, teacher: rng.randrange(len(rows))


def save_json(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
