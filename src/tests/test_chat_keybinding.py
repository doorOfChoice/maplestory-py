"""聊天唤起键：chat 动作默认 Enter、对话让位 E、旧配置文件自动迁移。"""

import pygame

from game.core.keybindings import KeyBindings


def test_chat_defaults_to_enter_and_talk_to_e():
    """新版默认：Enter 聚焦聊天框，对话键让位给 E。"""
    kb = KeyBindings()
    assert kb.key_of("chat") == pygame.K_RETURN
    assert kb.key_of("talk") == pygame.K_e
    assert kb.action_for(pygame.K_RETURN) == "chat"


def test_legacy_config_without_chat_migrates_enter_to_chat():
    """旧配置（无 chat 键、对话绑在 Enter）：迁移后 Enter 归聊天、对话回 E。"""
    kb = KeyBindings.from_dict({"keys": {
        "talk": pygame.K_RETURN, "attack": pygame.K_a}})
    assert kb.key_of("chat") == pygame.K_RETURN
    assert kb.key_of("talk") == pygame.K_e


def test_legacy_config_with_custom_talk_key_keeps_it():
    """旧配置里对话已改到他键：不动用户绑定，chat 照常默认 Enter。"""
    kb = KeyBindings.from_dict({"keys": {"talk": pygame.K_y}})
    assert kb.key_of("talk") == pygame.K_y
    assert kb.key_of("chat") == pygame.K_RETURN


def test_explicit_chat_binding_wins_over_migration():
    """配置里已显式绑了 chat（哪怕是别的键）：不再触发迁移。"""
    kb = KeyBindings.from_dict({"keys": {
        "talk": pygame.K_RETURN, "chat": pygame.K_t}})
    assert kb.key_of("chat") == pygame.K_t
