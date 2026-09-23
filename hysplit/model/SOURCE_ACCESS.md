# Obtaining the HYSPLIT model package or full source

The directories `distributions/` and `source/` are intentionally ready for the
gated NOAA files.

## Public research installer

The public Mac package is HYSPLIT 5.4.2 (May 2025). NOAA requires the
researcher to read the HYSPLIT use agreement, provide an email address, and
submit the agreement form:

<https://www.ready.noaa.gov/HYSPLIT_applehysp.php>

The corresponding Windows public package is:

<https://www.ready.noaa.gov/HYSPLIT_hytrial.php>

After downloading, place the untouched installer in `distributions/`. The
public package contains executables, GUI scripts, examples, test data,
documentation, and sample source code. NOAA states that its trajectory model
is unrestricted; the public dispersion executable cannot use forecast
meteorology for concentration calculations.

## Full non-commercial Linux source

NOAA's instructions are:

1. Register at <https://www.ready.noaa.gov/HYSPLIT_register.php>.
2. Request Linux source access from `arl.webmaster@noaa.gov`.
3. If access is approved, use the separately supplied SVN credentials and
   checkout instructions.
4. Place the checkout under `source/`.

Official source-access page:

<https://www.ready.noaa.gov/HYSPLIT_linux.php>

An offline copy of that page is in
[`../docs/manuals/HYSPLIT_Source_Access.html`](../docs/manuals/HYSPLIT_Source_Access.html).

