#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
senses.py — Eran's multisensory binding layer.

Emulated multisensory streams:
  - vision: face embedding (insightface 512-d)
  - hearing: Iddo's voice embedding (speaker-ID placeholder)
  - smell: fixed olfactory signature per person
  - touch: reciprocal active haptics (placeholder)

Binding rule: when ALL senses co-occur for Iddo, oxytocin bonus fires.

Returns a "sensory context" dict so grounded_ah.py can pass it to neuromod.py.
Later, this will drive multi-modal learning (not just picture -> /a/, but also
voice + smell + touch -> coordinated response).

Part 1b: Architecture & structure only. Placeholders are OK.
"""

import os
import sys
import numpy as np
import json

HERE = os.path.dirname(os.path.abspath(__file__))


class VisionSense:
    """Face embedding (from insightface via family.py)."""

    def __init__(self):
        self.embedding = None
        self.person = None
        self.confidence = 0.0

    def perceive(self, embedding, person='iddo', confidence=1.0):
        """
        Perceive a face.

        Args:
            embedding: np.ndarray (512,) face embedding
            person: str, person name ('iddo', 'alma', etc.)
            confidence: float 0-1, detection confidence
        """
        self.embedding = np.asarray(embedding, dtype=np.float32)
        self.person = person
        self.confidence = float(confidence)
        return self

    def to_dict(self):
        return {
            'embedding_shape': tuple(self.embedding.shape) if self.embedding is not None else None,
            'person': self.person,
            'confidence': float(self.confidence),
        }


class HearingSense:
    """Voice embedding (speaker-ID placeholder)."""

    def __init__(self):
        self.embedding = None
        self.speaker = None
        self.confidence = 0.0

    def perceive(self, voice_waveform=None, speaker='iddo', speaker_embedding=None, confidence=0.0):
        """
        Perceive a voice.

        Args:
            voice_waveform: np.ndarray audio (placeholder for real speaker-ID later)
            speaker: str, speaker name
            speaker_embedding: np.ndarray, speaker embedding (512-d placeholder)
            confidence: float 0-1, speaker-ID confidence
        """
        if speaker_embedding is None:
            # Placeholder: fixed speaker embedding for 'iddo'
            if speaker == 'iddo':
                np.random.seed(123)
                speaker_embedding = np.random.randn(512).astype(np.float32)
                speaker_embedding = speaker_embedding / (np.linalg.norm(speaker_embedding) + 1e-9)
            else:
                np.random.seed(456)
                speaker_embedding = np.random.randn(512).astype(np.float32)
                speaker_embedding = speaker_embedding / (np.linalg.norm(speaker_embedding) + 1e-9)

        self.embedding = speaker_embedding
        self.speaker = speaker
        self.confidence = float(confidence)
        return self

    def to_dict(self):
        return {
            'embedding_shape': tuple(self.embedding.shape) if self.embedding is not None else None,
            'speaker': self.speaker,
            'confidence': float(self.confidence),
        }


class SmellSense:
    """Olfactory signature (fixed per person, placeholder)."""

    def __init__(self):
        self.signature = None
        self.person = None
        self.intensity = 0.0

    def perceive(self, person='iddo', intensity=0.5):
        """
        Perceive an olfactory signature.

        Args:
            person: str, person name
            intensity: float 0-1, smell intensity
        """
        # Fixed olfactory signature per person (deterministic)
        np.random.seed(hash(person) % 2**31)
        sig = np.random.randn(64).astype(np.float32)
        sig = sig / (np.linalg.norm(sig) + 1e-9)

        self.signature = sig
        self.person = person
        self.intensity = float(intensity)
        return self

    def to_dict(self):
        return {
            'signature_shape': tuple(self.signature.shape) if self.signature is not None else None,
            'person': self.person,
            'intensity': float(self.intensity),
        }


class TouchSense:
    """Reciprocal haptic feedback (placeholder for hardware later)."""

    def __init__(self):
        self.pressure = None
        self.temperature = 37.0  # baseline human skin temp
        self.texture_id = None

    def perceive(self, pressure=0.0, temperature=37.0, texture_id='neutral'):
        """
        Perceive touch.

        Args:
            pressure: float, tactile pressure (0-1)
            temperature: float, skin temperature in Celsius
            texture_id: str, texture name ('smooth', 'rough', 'warm', etc.)
        """
        self.pressure = float(pressure)
        self.temperature = float(temperature)
        self.texture_id = str(texture_id)
        return self

    def to_dict(self):
        return {
            'pressure': float(self.pressure),
            'temperature': float(self.temperature),
            'texture_id': self.texture_id,
        }


class SensoryContext:
    """Unified multisensory context."""

    def __init__(self):
        self.vision = VisionSense()
        self.hearing = HearingSense()
        self.smell = SmellSense()
        self.touch = TouchSense()
        self.timestamp = None
        self.binding_strength = 0.0  # 0-1, how strongly senses are bound

    def bind(self, vision=True, hearing=True, smell=True, touch=True):
        """
        Compute binding strength: how many senses are currently active.

        Returns:
            float 0-1, binding strength (1.0 = all 4 senses active)
        """
        active = sum([
            vision and self.vision.embedding is not None,
            hearing and self.hearing.embedding is not None,
            smell and self.smell.signature is not None,
            touch and self.touch.pressure is not None,
        ])
        self.binding_strength = float(active / 4.0)
        return self.binding_strength

    def oxytocin_bonus(self, target_person='iddo'):
        """
        Oxytocin bonus: fire when ALL senses indicate Iddo is present.

        Returns:
            float 0-1, oxytocin boost (1.0 = strong bonding moment)
        """
        # All senses must agree on the person + be active
        senses_match_target = (
            (self.vision.person == target_person and self.vision.confidence > 0.5) and
            (self.hearing.speaker == target_person and self.hearing.confidence > 0.3) and
            (self.smell.person == target_person and self.smell.intensity > 0.2) and
            (self.touch.pressure > 0.1)  # active contact
        )

        if senses_match_target:
            # Strong multi-sensory binding
            return 1.0
        elif self.binding_strength > 0.5:
            # Weak bonding: some senses active
            return 0.5
        else:
            return 0.0

    def to_dict(self):
        """Serialize for logging."""
        return {
            'vision': self.vision.to_dict(),
            'hearing': self.hearing.to_dict(),
            'smell': self.smell.to_dict(),
            'touch': self.touch.to_dict(),
            'binding_strength': float(self.binding_strength),
        }


def acquire_sensory_context(picture_embedding=None, voice_waveform=None,
                             person='iddo', include_proprioception=False):
    """
    Acquire a full sensory context snapshot.

    This is the entry point: call this to build a context for a learning episode.

    Args:
        picture_embedding: np.ndarray (512,) face embedding
        voice_waveform: np.ndarray audio sample (unused for now, placeholder)
        person: str, person name
        include_proprioception: bool, include body sensing (placeholder)

    Returns:
        SensoryContext object
    """
    ctx = SensoryContext()

    # Vision
    if picture_embedding is not None:
        ctx.vision.perceive(picture_embedding, person=person, confidence=1.0)

    # Hearing: placeholder speaker-ID from person name
    ctx.hearing.perceive(voice_waveform, speaker=person, confidence=0.7)

    # Smell: deterministic per person
    ctx.smell.perceive(person=person, intensity=0.5)

    # Touch: weak contact baseline (hardware would provide real haptics)
    ctx.touch.perceive(pressure=0.3, temperature=36.8, texture_id='neutral')

    # Proprioception: TODO (body pose estimation, balance, etc.)

    # Compute binding
    ctx.bind(vision=(picture_embedding is not None),
             hearing=True,
             smell=True,
             touch=True)

    return ctx


if __name__ == "__main__":
    # Self-test
    print("[senses] self-test")

    # Acquire context with Iddo's picture
    np.random.seed(42)
    fake_iddo_emb = np.random.randn(512).astype(np.float32)
    fake_iddo_emb = fake_iddo_emb / (np.linalg.norm(fake_iddo_emb) + 1e-9)

    ctx = acquire_sensory_context(
        picture_embedding=fake_iddo_emb,
        voice_waveform=None,
        person='iddo',
    )

    print(f"[senses] acquired context for {ctx.vision.person}")
    print(f"[senses] binding strength: {ctx.binding_strength:.2f}")
    print(f"[senses] oxytocin bonus: {ctx.oxytocin_bonus():.2f}")
    print(f"[senses] context summary: {json.dumps(ctx.to_dict(), indent=2)}")

    print("[senses] self-test OK")
