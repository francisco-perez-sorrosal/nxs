"""Unit tests for StateProvider implementations."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from nxs.infrastructure.state import InMemoryStateProvider, FileStateProvider


class TestInMemoryStateProvider:
    """Test InMemoryStateProvider implementation."""

    @pytest.mark.asyncio
    async def test_save_and_load(self):
        """Test basic save and load operations."""
        provider = InMemoryStateProvider()
        test_data = {"key1": "value1", "key2": 42, "nested": {"a": 1, "b": 2}}

        # Save data
        await provider.save("test:key", test_data)

        # Load data
        loaded = await provider.load("test:key")
        assert loaded == test_data

    @pytest.mark.asyncio
    async def test_load_nonexistent_key(self):
        """Test loading a non-existent key returns None."""
        provider = InMemoryStateProvider()
        result = await provider.load("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_exists(self):
        """Test exists check."""
        provider = InMemoryStateProvider()
        test_data = {"data": "value"}

        # Key doesn't exist yet
        assert await provider.exists("test:key") is False

        # Save data
        await provider.save("test:key", test_data)

        # Key now exists
        assert await provider.exists("test:key") is True

    @pytest.mark.asyncio
    async def test_delete(self):
        """Test delete operation."""
        provider = InMemoryStateProvider()
        test_data = {"data": "value"}

        # Save and verify exists
        await provider.save("test:key", test_data)
        assert await provider.exists("test:key") is True

        # Delete
        await provider.delete("test:key")

        # Verify deleted
        assert await provider.exists("test:key") is False
        assert await provider.load("test:key") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self):
        """Test deleting a non-existent key is idempotent."""
        provider = InMemoryStateProvider()

        # Should not raise error
        await provider.delete("nonexistent")

    @pytest.mark.asyncio
    async def test_list_keys(self):
        """Test listing all keys."""
        provider = InMemoryStateProvider()

        # Save multiple keys
        await provider.save("session:1", {"id": 1})
        await provider.save("session:2", {"id": 2})
        await provider.save("config:main", {"setting": "value"})

        # List all keys
        all_keys = await provider.list_keys()
        assert len(all_keys) == 3
        assert "session:1" in all_keys
        assert "session:2" in all_keys
        assert "config:main" in all_keys

    @pytest.mark.asyncio
    async def test_list_keys_with_prefix(self):
        """Test listing keys with prefix filter."""
        provider = InMemoryStateProvider()

        # Save multiple keys
        await provider.save("session:1", {"id": 1})
        await provider.save("session:2", {"id": 2})
        await provider.save("config:main", {"setting": "value"})

        # List only session keys
        session_keys = await provider.list_keys(prefix="session:")
        assert len(session_keys) == 2
        assert "session:1" in session_keys
        assert "session:2" in session_keys
        assert "config:main" not in session_keys

    @pytest.mark.asyncio
    async def test_data_isolation(self):
        """Test that saved data is deep copied (isolated from mutations)."""
        provider = InMemoryStateProvider()
        original_data = {"value": [1, 2, 3]}

        # Save data
        await provider.save("test:key", original_data)

        # Mutate original
        original_data["value"].append(4)

        # Loaded data should not be affected
        loaded = await provider.load("test:key")
        assert loaded == {"value": [1, 2, 3]}

    def test_len_and_contains(self):
        """Test __len__ and __contains__ utility methods."""
        provider = InMemoryStateProvider()

        # Empty provider
        assert len(provider) == 0
        assert "test:key" not in provider

        # Use asyncio.run for async operations in sync test
        asyncio.run(provider.save("test:key", {"data": "value"}))

        # After adding data
        assert len(provider) == 1
        assert "test:key" in provider

    def test_clear_all(self):
        """Test clear_all utility method."""
        provider = InMemoryStateProvider()

        # Add some data
        asyncio.run(provider.save("key1", {"data": 1}))
        asyncio.run(provider.save("key2", {"data": 2}))
        assert len(provider) == 2

        # Clear all
        provider.clear_all()

        # Verify empty
        assert len(provider) == 0


class TestFileStateProvider:
    """Test FileStateProvider implementation."""

    @pytest.mark.asyncio
    async def test_save_and_load(self):
        """Test basic save and load operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = FileStateProvider(base_dir=tmpdir)
            test_data = {"key1": "value1", "key2": 42, "nested": {"a": 1, "b": 2}}

            # Save data
            await provider.save("test:key", test_data)

            # Verify file was created
            expected_file = Path(tmpdir) / "test__key.json"
            assert expected_file.exists()

            # Load data
            loaded = await provider.load("test:key")
            assert loaded == test_data

    @pytest.mark.asyncio
    async def test_load_nonexistent_key(self):
        """Test loading a non-existent key returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = FileStateProvider(base_dir=tmpdir)
            result = await provider.load("nonexistent")
            assert result is None

    @pytest.mark.asyncio
    async def test_exists(self):
        """Test exists check."""
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = FileStateProvider(base_dir=tmpdir)
            test_data = {"data": "value"}

            # Key doesn't exist yet
            assert await provider.exists("test:key") is False

            # Save data
            await provider.save("test:key", test_data)

            # Key now exists
            assert await provider.exists("test:key") is True

    @pytest.mark.asyncio
    async def test_delete(self):
        """Test delete operation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = FileStateProvider(base_dir=tmpdir)
            test_data = {"data": "value"}

            # Save and verify exists
            await provider.save("test:key", test_data)
            assert await provider.exists("test:key") is True

            # Delete
            await provider.delete("test:key")

            # Verify deleted
            assert await provider.exists("test:key") is False
            assert await provider.load("test:key") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self):
        """Test deleting a non-existent key is idempotent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = FileStateProvider(base_dir=tmpdir)

            # Should not raise error
            await provider.delete("nonexistent")

    @pytest.mark.asyncio
    async def test_list_keys(self):
        """Test listing all keys."""
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = FileStateProvider(base_dir=tmpdir)

            # Save multiple keys
            await provider.save("session:1", {"id": 1})
            await provider.save("session:2", {"id": 2})
            await provider.save("config:main", {"setting": "value"})

            # List all keys
            all_keys = await provider.list_keys()
            assert len(all_keys) == 3
            assert "session:1" in all_keys
            assert "session:2" in all_keys
            assert "config:main" in all_keys

    @pytest.mark.asyncio
    async def test_list_keys_with_prefix(self):
        """Test listing keys with prefix filter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = FileStateProvider(base_dir=tmpdir)

            # Save multiple keys
            await provider.save("session:1", {"id": 1})
            await provider.save("session:2", {"id": 2})
            await provider.save("config:main", {"setting": "value"})

            # List only session keys
            session_keys = await provider.list_keys(prefix="session:")
            assert len(session_keys) == 2
            assert "session:1" in session_keys
            assert "session:2" in session_keys
            assert "config:main" not in session_keys

    @pytest.mark.asyncio
    async def test_key_to_filename_conversion(self):
        """Test that special characters in keys are converted safely."""
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = FileStateProvider(base_dir=tmpdir)
            test_data = {"data": "value"}

            # Save with colon in key
            await provider.save("session:abc123", test_data)

            # Verify file uses __ instead of :
            expected_file = Path(tmpdir) / "session__abc123.json"
            assert expected_file.exists()

            # Load should still work
            loaded = await provider.load("session:abc123")
            assert loaded == test_data

    @pytest.mark.asyncio
    async def test_directory_creation(self):
        """Test that provider creates directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_dir = Path(tmpdir) / "nested" / "path"
            provider = FileStateProvider(base_dir=nested_dir)

            # Directory should be created
            assert nested_dir.exists()
            assert nested_dir.is_dir()

    @pytest.mark.asyncio
    async def test_atomic_write(self):
        """Test that writes are atomic (using temp file)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = FileStateProvider(base_dir=tmpdir)
            test_data = {"data": "value"}

            # Save data
            await provider.save("test:key", test_data)

            # Verify no .tmp file left behind
            tmp_files = list(Path(tmpdir).glob("*.tmp"))
            assert len(tmp_files) == 0

    @pytest.mark.asyncio
    async def test_get_file_path_utility(self):
        """Test get_file_path utility method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = FileStateProvider(base_dir=tmpdir)

            file_path = provider.get_file_path("session:123")
            assert file_path == Path(tmpdir) / "session__123.json"

    @pytest.mark.asyncio
    async def test_unicode_data(self):
        """Test that Unicode data is preserved correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = FileStateProvider(base_dir=tmpdir)
            test_data = {
                "english": "Hello",
                "spanish": "Hola",
                "chinese": "你好",
                "emoji": "🚀💻"
            }

            # Save and load
            await provider.save("test:unicode", test_data)
            loaded = await provider.load("test:unicode")

            assert loaded == test_data


class TestStateProviderComparison:
    """Test that both providers behave identically."""

    @pytest.mark.asyncio
    async def test_provider_compatibility(self):
        """Test that InMemory and File providers have identical behavior."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory_provider = InMemoryStateProvider()
            file_provider = FileStateProvider(base_dir=tmpdir)

            test_data = {"key": "value", "number": 123}

            # Same operations on both providers
            for provider in [memory_provider, file_provider]:
                await provider.save("test:key", test_data)
                assert await provider.exists("test:key") is True
                loaded = await provider.load("test:key")
                assert loaded == test_data

                await provider.delete("test:key")
                assert await provider.exists("test:key") is False
