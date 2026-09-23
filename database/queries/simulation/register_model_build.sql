INSERT INTO simulation.model_build (
    model_name, model_version, source_sha256, patch_set_sha256,
    executable_sha256, container_digest, toolchain, enabled
)
VALUES (
    %(model_name)s, %(model_version)s, %(source_sha256)s, %(patch_set_sha256)s,
    %(executable_sha256)s, %(container_digest)s, %(toolchain)s::jsonb, true
)
ON CONFLICT (
    model_name, model_version, source_sha256, patch_set_sha256, executable_sha256
) DO UPDATE
SET toolchain = EXCLUDED.toolchain,
    container_digest = COALESCE(EXCLUDED.container_digest, simulation.model_build.container_digest),
    enabled = true
RETURNING id, model_name, model_version, executable_sha256;
