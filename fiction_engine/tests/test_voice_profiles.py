"""test_voice_profiles.py — get_author_voices, get_author_voice_by_source"""
import pytest


class TestGetAuthorVoices:
    def test_nonempty_list(self):
        from engine.voice_profiles import get_author_voices
        result = get_author_voices()
        assert isinstance(result, list) and len(result) > 0

    def test_required_keys_present(self):
        from engine.voice_profiles import get_author_voices
        for v in get_author_voices():
            for k in ("name","source","profile"):
                assert k in v, f"'{k}' missing in {v.get('name')}"

    def test_profiles_nonempty(self):
        from engine.voice_profiles import get_author_voices
        for v in get_author_voices():
            assert v["profile"].strip(), f"empty profile: {v['name']}"

    def test_sources_unique(self):
        from engine.voice_profiles import get_author_voices
        sources = [v["source"] for v in get_author_voices()]
        assert len(sources) == len(set(sources))


class TestGetAuthorVoiceBySource:
    def test_first_known_source_found(self):
        from engine.voice_profiles import get_author_voices, get_author_voice_by_source
        voices = get_author_voices()
        if not voices: pytest.skip("no voices defined")
        src = voices[0]["source"]
        result = get_author_voice_by_source(src)
        assert result is not None and result["source"] == src

    def test_unknown_returns_none(self):
        from engine.voice_profiles import get_author_voice_by_source
        assert get_author_voice_by_source("nonexistent_xyz_123") is None

    def test_empty_returns_none(self):
        from engine.voice_profiles import get_author_voice_by_source
        assert get_author_voice_by_source("") is None

    def test_sapkowski_present(self):
        from engine.voice_profiles import get_author_voice_by_source
        r = get_author_voice_by_source("sapkowski")
        assert r is not None and "profile" in r
