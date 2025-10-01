# --- Original PS1 without Conda env ---
ORIGINAL_PS1='\[\033]0;$TITLEPREFIX:$PWD\007\]\n\[\033[32m\]\u@\h \[\033[35m\]$MSYSTEM \[\033[33m\]\w\[\033[36m\]$(__git_ps1)\[\033[0m\]\n\$ '

# --- Initialize PS1 ---
export PS1="$ORIGINAL_PS1"

# --- Function to update PS1 with active Conda environment ---
function add_conda_to_ps1() {
    local env_name="$1"
    if [[ -z "$env_name" ]]; then
        # No active environment, revert to original
        PS1="$ORIGINAL_PS1"
    else
        # Prepend env name to original PS1
        if [[ "$env_name" == "base" ]]; then
            PS1="\[\033]0;$TITLEPREFIX:$PWD\007\]\n\[\033[37m\]($env_name)\[\033[0m\]$ORIGINAL_PS1"  # gray for base
        else
            PS1="\[\033]0;$TITLEPREFIX:$PWD\007\]\n\[\033[32m\]($env_name)\[\033[0m\]$ORIGINAL_PS1"  # green for others
        fi
    fi
}

# --- Wrapper for conda command ---
function conda() {
    if [[ "$1" == "activate" ]]; then
        # Run original conda activate
        command conda "$@"
        # Update PS1 with current environment
        add_conda_to_ps1 "$CONDA_DEFAULT_ENV"
    elif [[ "$1" == "deactivate" ]]; then
        # Run original conda deactivate
        command conda "$@"
        # Update PS1 after deactivation
        add_conda_to_ps1 "$CONDA_DEFAULT_ENV"
    else
        # Other conda commands pass through
        command conda "$@"
    fi
}
