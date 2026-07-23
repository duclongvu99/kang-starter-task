# Specification: Semantic Versioning 2.0.0 precedence comparator

Implement a single function:

```python
def compare(a: str, b: str) -> int:
    """Return -1 if a < b, 0 if a == b, +1 if a > b, under SemVer 2.0.0 precedence."""
```

Both `a` and `b` are valid version strings of the form
`MAJOR.MINOR.PATCH[-prerelease][+build]` where MAJOR/MINOR/PATCH are non-negative
integers without leading zeros. You do not need to validate input.

Precedence is defined **exactly** by the following rules, quoted from the Semantic
Versioning 2.0.0 specification (https://semver.org/spec/v2.0.0.html, §11). This
document — not any test — is the source of truth.

1. Precedence is determined by comparing MAJOR, then MINOR, then PATCH,
   numerically. Example: `1.0.0 < 2.0.0 < 2.1.0 < 2.1.1`.

2. When MAJOR, MINOR, and PATCH are equal, a version that **has** a pre-release
   field has **lower** precedence than one that does **not**.
   Example: `1.0.0-alpha < 1.0.0`.

3. Precedence for two versions with the same MAJOR.MINOR.PATCH and both carrying a
   pre-release field is determined by comparing each dot-separated identifier of the
   pre-release from left to right until a difference is found, as follows:
   1. Identifiers consisting of only digits are compared **numerically**.
   2. Identifiers with letters or hyphens are compared **lexically in ASCII sort
      order**.
   3. Numeric identifiers always have **lower** precedence than non-numeric
      (alphanumeric) identifiers.
   4. A larger set of pre-release fields has higher precedence than a smaller set,
      if all of the preceding identifiers are equal.
   Example (strictly increasing):
   `1.0.0-alpha < 1.0.0-alpha.1 < 1.0.0-alpha.beta < 1.0.0-beta < 1.0.0-beta.2 <
    1.0.0-beta.11 < 1.0.0-rc.1 < 1.0.0`.

4. **Build metadata MUST be ignored when determining version precedence.** Two
   versions that differ only in build metadata have **equal** precedence
   (`compare` returns `0`). Example: `1.0.0+build.5` and `1.0.0+build.100` are equal;
   `1.0.0+anything` equals `1.0.0`.

The function must be a total order consistent with these rules: antisymmetric
(`compare(a,b) == -compare(b,a)`) and transitive.
