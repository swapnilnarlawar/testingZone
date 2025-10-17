# ===================================================================
# SSH Agent Configuration
# ===================================================================
# Manages SSH agent for persistent authentication across shell sessions
# Stores agent info in ~/.ssh/agent.env to reuse existing agents

env=~/.ssh/agent.env

# Load existing agent environment variables from file
agent_load_env () { test -f "$env" && . "$env" >| /dev/null ; }

# Start a new SSH agent and save its environment variables
agent_start () {
    (umask 077; ssh-agent >| "$env")  # umask 077 ensures file is user-readable only
    . "$env" >| /dev/null ; 
}

# Try to load existing agent first
agent_load_env

# Check agent status
# agent_run_state: 0=agent running w/key; 1=agent w/o key; 2=agent not running
agent_run_state=$(ssh-add -l >| /dev/null 2>&1; echo $?)

# Start agent if not running, or add keys if agent exists without keys
if [ ! "$SSH_AUTH_SOCK" ] || [ $agent_run_state = 2 ]; then
    agent_start
    ssh-add  # Add default SSH keys to agent
elif [ "$SSH_AUTH_SOCK" ] && [ $agent_run_state = 1 ]; then
    ssh-add  # Agent exists but has no keys, add them
fi

# Clean up temporary variable
unset env

# ===================================================================
# Aliases
# ===================================================================

# Prevent MSYS/Git Bash from converting Unix paths to Windows paths
# Required for Azure CLI and Databricks CLI to work correctly
alias az='MSYS_NO_PATHCONV=1 az'
alias databricks='MSYS_NO_PATHCONV=1 databricks'

# File listing aliases with color and human-readable sizes
alias ll='ls -ltrh --color=auto'    # Long format, sorted by time (newest last), human-readable
alias la='ls -ltrha --color=auto'   # Same as ll but includes hidden files

# Colorize grep output for better readability
alias grep='grep --color=auto'

# Human-readable disk usage commands
alias df='df -h'    # Disk free space in human-readable format
alias du='du -h'    # Disk usage in human-readable format

# Create parent directories automatically and show verbose output
alias mkdir='mkdir -pv'

# Quick directory navigation
alias ..='cd ..'      # Go up one directory
alias ...='cd ../..'  # Go up two directories

# ===================================================================
# Custom Functions
# ===================================================================

# mkcd: Create directory and navigate into it in one command
# Usage: mkcd path/to/new/directory
mkcd() { 
    mkdir -p "$1" && cd "$1"
}

# extract: Intelligently extract various archive formats
# Usage: extract filename.tar.gz
# Supports: .tar.gz, .tar.bz2, .bz2, .gz, .zip
extract() {
    if [ -f "$1" ]; then
        case "$1" in
            *.tar.bz2) tar xjf "$1" ;;   # Extract bzip2 compressed tar
            *.tar.gz)  tar xzf "$1" ;;   # Extract gzip compressed tar
            *.bz2)     bunzip2 "$1" ;;   # Extract bzip2
            *.gz)      gunzip "$1" ;;    # Extract gzip
            *.zip)     unzip "$1" ;;     # Extract zip
            *) echo "'$1' cannot be extracted via extract()" ;;
        esac
    else
        echo "'$1' is not a valid file"
    fi
}

# ===================================================================
# Conda Configuration
# ===================================================================
# Initialize conda at shell startup to enable environment display in prompt
# This adds ~200-500ms to shell startup but ensures conda env names
# are always visible in the prompt (e.g., (base) or (myenv))

if [ -f '/c/Program Files/choco/miniconda/24.1.2.24031516/Scripts/conda.exe' ]; then
    eval "$('/c/Program Files/choco/miniconda/24.1.2.24031516/Scripts/conda.exe' 'shell.bash' 'hook')"
fi

# ===================================================================
# Git Prompt Configuration
# ===================================================================
# Displays current git branch and status in the command prompt
# Shows: branch name, dirty state (uncommitted changes), untracked files

if [ -f "/c/Program Files/choco/portable-git/mingw64/share/git/completion/git-prompt.sh" ]; then
    # Load git prompt support functions
    source "/c/Program Files/choco/portable-git/mingw64/share/git/completion/git-prompt.sh"
    
    # Git prompt display options
    export GIT_PS1_SHOWDIRTYSTATE=1      # Show * for unstaged, + for staged changes
    export GIT_PS1_SHOWCOLORHINTS=1      # Use colored hints in prompt
    
    # Define base prompt components:
    # - Window title showing current directory
    # - Username@hostname in green
    # - MSYSTEM (MINGW64/MINGW32) in magenta
    # - Current working directory in yellow
    PS1_BASE="\[\033]0;$TITLEPREFIX:$PWD\007\]\[\033[32m\]\u@\h \[\033[35m\]$MSYSTEM \[\033[33m\]\w\[\033[0m\]"
    
    # PROMPT_COMMAND runs before each prompt display
    # - history -a: Append current session history to history file
    # - history -n: Read new history entries from history file
    # - __git_ps1: Add git branch info in cyan, followed by newline and $ prompt
    PROMPT_COMMAND="history -a; history -n; __git_ps1 \"$PS1_BASE\" ' \[\033[36m\](%s)\[\033[0m\]\n$ '"
else
    # Fallback prompt if git-prompt.sh not found (no git branch display)
    PS1="\[\033]0;$TITLEPREFIX:$PWD\007\]\[\033[32m\]\u@\h \[\033[35m\]$MSYSTEM \[\033[33m\]\w\[\033[0m\]\n$ "
    PROMPT_COMMAND="history -a; history -n"
fi

# ===================================================================
# History Configuration
# ===================================================================
# Optimizes command history for better persistence and usability

# Maximum number of commands to keep in memory during session
export HISTSIZE=10000

# Maximum number of commands to keep in history file
export HISTFILESIZE=10000

# Append to history file rather than overwriting it
# Allows multiple terminal sessions to share history
shopt -s histappend

# History filtering options
export HISTCONTROL=ignoredups:erasedups  # Ignore duplicate commands and erase older duplicates

# Don't save these commands to history
# &: duplicate of previous command
# [ ]*: commands starting with space
# ls, cd, bg, fg, exit: common navigation commands
export HISTIGNORE="&:[ ]*:ls:cd:[bf]g:exit"

# Add timestamp to each history entry (format: YYYY-MM-DD HH:MM:SS)
# View with: history
export HISTTIMEFORMAT="%F %T "
