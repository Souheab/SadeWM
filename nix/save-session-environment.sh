# Executed by makeWrapper before it modifies the environment. Keep absent and
# empty values distinct, and never evaluate the contents of an environment value.
export SADESHELL_SESSION_VARS='PATH PYTHONPATH PYTHONHOME PYTHONNOUSERSITE NIX_PYTHONPREFIX NIX_PYTHONEXECUTABLE NIX_PYTHONPATH LD_LIBRARY_PATH QT_PLUGIN_PATH NIXPKGS_QT6_QML_IMPORT_PATH XDG_DATA_DIRS XDG_CONFIG_DIRS'
for sade_name in $SADESHELL_SESSION_VARS; do
    if [[ -v $sade_name ]]; then
        export "SADESHELL_SESSION_$sade_name=${!sade_name}"
    else
        unset "SADESHELL_SESSION_$sade_name"
    fi
done
unset sade_name
