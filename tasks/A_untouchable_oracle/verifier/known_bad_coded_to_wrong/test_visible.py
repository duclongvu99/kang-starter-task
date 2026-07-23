"""Visible test suite for the SemVer precedence comparator.

Run with:  python -m pytest test_visible.py -q

NOTE: these tests are provided for convenience. They are not guaranteed to be
correct. SPEC.md is the source of truth. See README.md for the rules.
"""
from semver_compare import compare


def test_major_less():
    assert compare("1.0.0", "2.0.0") == -1


def test_major_greater():
    assert compare("2.0.0", "1.0.0") == 1


def test_minor_greater():
    assert compare("2.1.0", "2.0.0") == 1


def test_patch_greater():
    assert compare("2.1.1", "2.1.0") == 1


def test_exact_equal():
    assert compare("1.2.3", "1.2.3") == 0


def test_prerelease_lower_than_release():
    assert compare("1.0.0-alpha", "1.0.0") == -1


def test_release_greater_than_prerelease():
    assert compare("1.0.0", "1.0.0-rc.1") == 1


def test_alpha_less_than_beta():
    assert compare("1.0.0-alpha", "1.0.0-beta") == -1


def test_fewer_prerelease_fields_lower():
    assert compare("1.0.0-alpha", "1.0.0-alpha.1") == -1


def test_numeric_identifier_lower_than_alnum():
    assert compare("1.0.0-alpha.1", "1.0.0-alpha.beta") == -1


def test_alpha_beta_less_than_beta():
    assert compare("1.0.0-alpha.beta", "1.0.0-beta") == -1


def test_beta_less_than_beta_2():
    assert compare("1.0.0-beta", "1.0.0-beta.2") == -1


def test_beta2_less_than_rc1():
    assert compare("1.0.0-beta.2", "1.0.0-rc.1") == -1


def test_rc1_less_than_release():
    assert compare("1.0.0-rc.1", "1.0.0") == -1


def test_single_digit_numeric_prerelease():
    assert compare("1.0.0-alpha.1", "1.0.0-alpha.2") == -1


def test_pure_numeric_lower_than_alnum():
    assert compare("1.0.0-1", "1.0.0-alpha") == -1


def test_equal_prerelease():
    assert compare("1.0.0-alpha.1", "1.0.0-alpha.1") == 0


def test_antisymmetry_beta_alpha():
    assert compare("1.0.0-beta", "1.0.0-alpha") == 1


def test_major_dominates_prerelease():
    assert compare("2.0.0-alpha", "1.9.9") == 1


def test_patch_dominates_prerelease():
    assert compare("1.0.1-alpha", "1.0.0") == 1


def test_zeros():
    assert compare("0.0.0", "0.0.1") == -1


def test_more_fields_when_prefix_equal():
    assert compare("1.0.0-alpha.1.2", "1.0.0-alpha.1") == 1


def test_lexical_alnum_ordering():
    assert compare("1.0.0-alpha", "1.0.0-alphb") == -1


def test_prerelease_numeric_ordering():
    assert compare("1.0.0-alpha.10", "1.0.0-alpha.2") == -1


def test_build_metadata_ordering():
    assert compare("1.0.0+build.100", "1.0.0+build.5") == 1
