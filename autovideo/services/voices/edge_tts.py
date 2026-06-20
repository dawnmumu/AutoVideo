from pathlib import Path
from typing import Any


class EdgeTtsProvider:
    async def list_voices(self) -> list[dict[str, Any]]:
        import edge_tts

        return await edge_tts.list_voices()

    async def synthesize_to_file(
        self,
        *,
        text: str,
        voice_id: str,
        output_path: Path,
        rate: str,
        volume: str,
        pitch: str,
    ) -> None:
        import edge_tts

        communicate = edge_tts.Communicate(
            text,
            voice_id,
            rate=rate,
            volume=volume,
            pitch=pitch,
        )
        await communicate.save(str(output_path))
