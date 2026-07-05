"""
test_weather.py — Tests para weather feature.

Valida:
- get_match_weather() retorna schema correcto
- available=False cuando no hay datos
- Derivados correctos (extreme_heat, wet, high_humidity)
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from predict.features import get_match_weather


class TestGetMatchWeather:
    """Tests para get_match_weather()."""

    def test_returns_dict(self, conn):
        """Retorna dict con todas las keys esperadas."""
        # Buscar un fixture con weather
        row = conn.execute(
            "SELECT fixture_id FROM match_weather LIMIT 1"
        ).fetchone()
        if row is None:
            pytest.skip("No hay weather data en BD todavía")
        result = get_match_weather(conn, row[0])
        assert isinstance(result, dict)
        assert "available" in result
        assert "temperature_c" in result
        assert "humidity_pct" in result
        assert "wind_kph" in result
        assert "precipitation_mm" in result
        assert "conditions" in result
        assert "is_extreme_heat" in result
        assert "is_wet" in result
        assert "is_high_humidity" in result

    def test_no_data_returns_unavailable(self, conn):
        """Fixture sin weather retorna available=False."""
        # Buscar un fixture sin weather (que tenga ID pero no en match_weather)
        row = conn.execute("""
            SELECT f.id FROM fixtures f
            WHERE f.league_id = 743
              AND NOT EXISTS (SELECT 1 FROM match_weather WHERE fixture_id = f.id)
            LIMIT 1
        """).fetchone()
        if row is None:
            pytest.skip("Todos los fixtures tienen weather")
        result = get_match_weather(conn, row[0])
        assert result["available"] is False
        assert result["temperature_c"] is None

    def test_extreme_heat_threshold(self, conn):
        """is_extreme_heat es True si temp > 32°C."""
        row = conn.execute(
            "SELECT fixture_id, temperature_c FROM match_weather LIMIT 1"
        ).fetchone()
        if row is None:
            pytest.skip("No hay weather data")
        result = get_match_weather(conn, row[0])
        if result["temperature_c"] is not None:
            expected = result["temperature_c"] > 32
            assert result["is_extreme_heat"] == expected

    def test_wet_threshold(self, conn):
        """is_wet es True si precipitación > 0.5mm."""
        row = conn.execute(
            "SELECT fixture_id, precipitation_mm FROM match_weather LIMIT 1"
        ).fetchone()
        if row is None:
            pytest.skip("No hay weather data")
        result = get_match_weather(conn, row[0])
        if result["precipitation_mm"] is not None:
            expected = result["precipitation_mm"] > 0.5
            assert result["is_wet"] == expected

    def test_high_humidity_threshold(self, conn):
        """is_high_humidity es True si humedad > 80%."""
        row = conn.execute(
            "SELECT fixture_id, humidity_pct FROM match_weather LIMIT 1"
        ).fetchone()
        if row is None:
            pytest.skip("No hay weather data")
        result = get_match_weather(conn, row[0])
        if result["humidity_pct"] is not None:
            expected = result["humidity_pct"] > 80
            assert result["is_high_humidity"] == expected

    def test_invalid_fixture_returns_unavailable(self, conn):
        """Fixture ID inválido retorna available=False."""
        result = get_match_weather(conn, -999)
        assert result["available"] is False


class TestWeatherIntegration:
    """Tests de integración con get_full_feature_set()."""

    def test_weather_in_full_feature_set(self, conn, team_ids, mid_season_date):
        """get_full_feature_set() incluye weather cuando hay fixture_id."""
        # Buscar un fixture con weather
        row = conn.execute("""
            SELECT f.id FROM fixtures f
            WHERE f.league_id = 743
              AND EXISTS (SELECT 1 FROM match_weather WHERE fixture_id = f.id)
            LIMIT 1
        """).fetchone()
        if row is None:
            pytest.skip("No hay weather data todavía")

        result = __import__('predict.features', fromlist=['get_full_feature_set']).get_full_feature_set(
            conn,
            home_team_id=team_ids["america"],
            away_team_id=team_ids["chivas"],
            fixture_date=mid_season_date,
            season_id=23636,
            fixture_id=row[0],
        )
        assert "weather" in result
        assert result["weather"]["available"] is True
        assert result["weather"]["temperature_c"] is not None