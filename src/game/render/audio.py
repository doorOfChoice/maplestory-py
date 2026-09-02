"""音频：BGM 循环 + 音效。全部从 Sound.wz 内嵌字节流直接加载。

pygame.mixer.music 支持从 BytesIO 流式播放（BGM，长音频），
pygame.mixer.Sound 支持短音效（Jump / LevelUp / PickUpItem / IncEXP…）。
audio 初始化失败时静默降级为无声（不阻塞游戏）。
"""

from __future__ import annotations

import io
import threading
from typing import Dict, Optional

import pygame

from game.render.assets import Assets


class Audio:
    def __init__(self, assets: Assets, bgm_path: str):
        self.assets = assets
        self.bgm_path = bgm_path
        self._enabled = False
        self._sounds: Dict[str, pygame.mixer.Sound] = {}
        self._lock = threading.Lock()
        self._init_mixer()
        if self._enabled:
            self._preload_sfx()

    def _init_mixer(self) -> None:
        try:
            pygame.mixer.pre_init(44100, -16, 2, 512)
            pygame.mixer.init()
            self._enabled = True
        except Exception:
            self._enabled = False

    # ── BGM ────────────────────────────────────────────────────────
    def play_bgm(self, volume: float = 0.6) -> None:
        if not self._enabled or not self.bgm_path:
            return
        data = self.assets.sound_bytes(self.bgm_path)
        if not data:
            return
        try:
            pygame.mixer.music.load(io.BytesIO(data))
            pygame.mixer.music.set_volume(volume)
            pygame.mixer.music.play(-1)
        except Exception:
            pass

    def stop_bgm(self) -> None:
        if self._enabled:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass

    # ── SFX ────────────────────────────────────────────────────────
    def _preload_sfx(self) -> None:
        for name in ("Jump", "LevelUp", "PickUpItem", "DropItem", "IncEXP",
                     "QuestClear", "GameIn", "Portal"):
            try:
                data = self.assets.sound_bytes(f"Game.img/{name}")
                if data:
                    self._sounds[name] = pygame.mixer.Sound(file=io.BytesIO(data))
            except Exception:
                pass

    def play(self, name: str, volume: float = 0.7) -> None:
        if not self._enabled:
            return
        snd = self._sounds.get(name)
        if snd is None:
            return
        try:
            snd.set_volume(volume)
            snd.play()
        except Exception:
            pass

    def _sfx(self, key: str, path: str) -> Optional[pygame.mixer.Sound]:
        """按键取音效，未预载则从 Sound.wz 惰性解码并缓存。"""
        snd = self._sounds.get(key)
        if snd is None:
            try:
                data = self.assets.sound_bytes(path)
                if data:
                    snd = pygame.mixer.Sound(file=io.BytesIO(data))
                    self._sounds[key] = snd
            except Exception:
                return None
        return snd

    def play_attack(self, equips, volume: float = 0.8) -> None:
        """武器攻击音效：按装备武器的 sfx 组名取 Sound/Weapon.img/{sfx}/Attack。"""
        if not self._enabled:
            return
        try:
            sfx = self.assets.weapon_sfx(list(equips))
        except Exception:
            sfx = "barehands"
        snd = self._sfx(f"Weapon/{sfx}/Attack", f"Weapon/{sfx}/Attack")
        if snd is None:
            return
        try:
            snd.set_volume(volume)
            snd.play()
        except Exception:
            pass

    def play_skill_cast(self, skill_id, equips, volume: float = 0.8) -> None:
        """技能施放音效：Sound/Skill.img/{skillId}/Use，缺失回退武器攻击音。"""
        if not self._enabled:
            return
        snd = None
        if skill_id is not None:
            key = f"Skill/{skill_id}/Use"
            snd = self._sfx(key, key)
        if snd is None:
            self.play_attack(equips, volume)
            return
        try:
            snd.set_volume(volume)
            snd.play()
        except Exception:
            pass

    def close(self) -> None:
        self.stop_bgm()
