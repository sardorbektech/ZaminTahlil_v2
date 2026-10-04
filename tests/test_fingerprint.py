"""Fingerprint hisoblash va deduplikatsiya testlari."""

from backend.app.pipeline.fingerprint import compute_recon_fingerprint


def test_fingerprint_deterministic_and_sorted():
    aoi_1 = {
        "type": "Polygon",
        "coordinates": [[[69.2, 41.3], [69.3, 41.3], [69.3, 41.4], [69.2, 41.3]]],
    }
    # Koordinata tartibi bir xil, lekin sahnalar boshqa tartibda berilsa ham bir xil bo'lishi kerak
    scenes_a = ["S2A_002", "S2A_001", "S1A_001"]
    scenes_b = ["S1A_001", "S2A_001", "S2A_002"]

    fp1 = compute_recon_fingerprint(aoi_1, scenes_a)
    fp2 = compute_recon_fingerprint(aoi_1, scenes_b)

    assert fp1 == fp2
    assert len(fp1) == 32  # 32 baytli SHA-256
