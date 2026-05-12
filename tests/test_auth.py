from research_radar.auth import hash_password, verify_password


def test_password_hash_round_trip() -> None:
    encoded = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong", encoded)


def test_example_password_hash_matches_readme() -> None:
    encoded = (
        "pbkdf2_sha256$260000$lxPF9IATsBF4N4qL3cz5aw"
        "$X6hD4PkQ7yPbDNk9hwa2LVrGdi6HKYwmi2RGVT2HEMk"
    )
    assert verify_password("research-radar", encoded)
