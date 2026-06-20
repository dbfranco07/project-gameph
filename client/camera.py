"""Camera / viewport that follows the player's hero."""

from shared.config import SCREEN_WIDTH, SCREEN_HEIGHT, MAP_WIDTH, MAP_HEIGHT


class Camera:
    def __init__(self) -> None:
        self.x = 0.0  # top-left corner in world coords
        self.y = 0.0

    def follow(self, world_x: float, world_y: float) -> None:
        """Center the camera on a world position, clamped to map edges."""
        self.x = world_x - SCREEN_WIDTH / 2
        self.y = world_y - SCREEN_HEIGHT / 2
        self._clamp()

    def pan(self, dx: float, dy: float) -> None:
        """Move the camera by a delta (free roam), clamped to map edges."""
        self.x += dx
        self.y += dy
        self._clamp()

    def _clamp(self) -> None:
        # Clamp so we don't show beyond the map. If the map is smaller than the
        # screen on an axis, pin to 0.
        self.x = max(0, min(max(0, MAP_WIDTH - SCREEN_WIDTH), self.x))
        self.y = max(0, min(max(0, MAP_HEIGHT - SCREEN_HEIGHT), self.y))

    def world_to_screen(self, wx: float, wy: float) -> tuple[int, int]:
        """Convert world coordinates to screen pixel coordinates."""
        return int(wx - self.x), int(wy - self.y)

    def screen_to_world(self, sx: int, sy: int) -> tuple[float, float]:
        """Convert screen pixel coordinates to world coordinates."""
        return sx + self.x, sy + self.y
