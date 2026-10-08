"""Unit tests for libraries/domain — validation behavior only (no I/O,
no plugin-sdk). This is what the CI 'unit test' stage (W0-2) runs."""

from __future__ import annotations

import pytest

from libraries.domain.frequency import Frequency
from libraries.domain.position import ENUPosition, GeoPosition
from libraries.domain.radio import Antenna, Radio, Receiver, Transmitter


class TestFrequency:
    def test_valid_construction(self) -> None:
        f = Frequency(center_hz=145.5e6, bandwidth_hz=12.5e3)
        assert f.lower_hz == pytest.approx(145.5e6 - 6.25e3)
        assert f.upper_hz == pytest.approx(145.5e6 + 6.25e3)

    def test_rejects_non_positive_center(self) -> None:
        with pytest.raises(ValueError):
            Frequency(center_hz=0, bandwidth_hz=12.5e3)
        with pytest.raises(ValueError):
            Frequency(center_hz=-1, bandwidth_hz=12.5e3)

    def test_rejects_non_positive_bandwidth(self) -> None:
        with pytest.raises(ValueError):
            Frequency(center_hz=145.5e6, bandwidth_hz=0)

    def test_overlap_detection(self) -> None:
        a = Frequency(center_hz=145.5e6, bandwidth_hz=25e3)
        b = Frequency(center_hz=145.51e6, bandwidth_hz=25e3)
        c = Frequency(center_hz=146.0e6, bandwidth_hz=25e3)
        assert a.overlaps(b)
        assert not a.overlaps(c)


class TestGeoPosition:
    def test_valid_construction(self) -> None:
        p = GeoPosition(lat=45.0, lon=6.0, alt_m=1200.0)
        assert p.lat == 45.0

    def test_default_altitude_is_zero(self) -> None:
        p = GeoPosition(lat=0.0, lon=0.0)
        assert p.alt_m == 0.0

    @pytest.mark.parametrize("lat", [90.1, -90.1])
    def test_rejects_out_of_range_lat(self, lat: float) -> None:
        with pytest.raises(ValueError):
            GeoPosition(lat=lat, lon=0.0)

    @pytest.mark.parametrize("lon", [180.1, -180.1])
    def test_rejects_out_of_range_lon(self, lon: float) -> None:
        with pytest.raises(ValueError):
            GeoPosition(lat=0.0, lon=lon)


class TestENUPosition:
    def test_defaults_up_to_zero(self) -> None:
        p = ENUPosition(east_m=10.0, north_m=20.0)
        assert p.up_m == 0.0


class TestRadio:
    def test_round_trip_construction(self) -> None:
        antenna = Antenna(antenna_type="dipole", gain_dBi=2.15, height_m=10.0)
        radio = Radio(
            id="RADIO-001",
            frequency=Frequency(center_hz=145.5e6, bandwidth_hz=12.5e3),
            transmitter=Transmitter(power_watt=10.0),
            receiver=Receiver(sensitivity_dBm=-120.0, noise_figure_dB=5.0),
            antenna=antenna,
            position=GeoPosition(lat=45.0, lon=6.0),
        )
        assert radio.id == "RADIO-001"
        assert radio.local_position is None  # resolved later by World Engine

    def test_default_antenna_pattern_is_omni(self) -> None:
        antenna = Antenna(antenna_type="dipole", gain_dBi=2.15, height_m=10.0)
        # assert antenna.pattern(azimuth := 90.0, elevation := 10.0) == 0.0
        azimuth_deg, elevation_deg = 90.0, 10.0
        assert antenna.pattern(azimuth_deg, elevation_deg) == 0.0
