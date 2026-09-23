from pathlib import Path

from weather_ingest.naps_pm25 import read_naps_pm25


def test_naps_hour_ending_local_standard_time_to_utc(tmp_path: Path) -> None:
    path = tmp_path / "PM25.csv"
    hours = ",".join(f"H{hour:02d}//H{hour:02d}" for hour in range(1, 25))
    values = ",".join(["10"] * 24)
    path.write_text(
        "File generated on,2026-01-01\n\n"
        f"Pollutant//Polluant,Method Code//Code Méthode,NAPS ID//Identifiant SNPA,"
        f"City//Ville,Province/Territory//Province/Territoire,Latitude//Latitude,"
        f"Longitude//Longitude,Date//Date,{hours}\n"
        f"PM2.5,184,010001,Test,NS,45,-63,2023-06-01,{values}\n"
    )
    observations, manifest = read_naps_pm25(path)
    assert len(observations) == 24
    assert observations[0].interval_end_utc.isoformat() == "2023-06-01T05:00:00+00:00"
    assert observations[-1].interval_end_utc.isoformat() == "2023-06-02T04:00:00+00:00"
    assert manifest["primary_methods"] == {"010001": "184"}
