from pathlib import Path

from weather_ingest.caliop_profiles import read_caliop_layer_csv


def test_caliop_source_neutral_layer_contract(tmp_path: Path) -> None:
    path = tmp_path / "layers.csv"
    path.write_text(
        "profile_id,event_id,observed_at_utc,latitude,longitude,base_agl_m,"
        "top_agl_m,feature_type,subtype,horizontal_averaging_km,qa_status\n"
        "p1,e1,2023-06-01T12:00:00Z,45,-75,1000,3000,aerosol,smoke,5,accepted\n"
    )
    layers = read_caliop_layer_csv(path)
    assert layers[0].midpoint_agl_m == 2000
    assert layers[0].source_sha256
