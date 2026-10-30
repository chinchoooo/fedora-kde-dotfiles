# PATH for user-level tools
if ! [[ "$PATH" =~ "$HOME/.local/bin:$HOME/bin:" ]]; then
    PATH="$HOME/.local/bin:$HOME/bin:$PATH"
fi
export PATH

# gh follows the folder: pick the token of the account that owns the folder (gh auth ... is left alone)
gh() {
    local acct=""
    case "$PWD/" in
        "$HOME"/work-b/*) acct=ACCOUNT_B ;;
        "$HOME"/code/*)   acct=ACCOUNT_A ;;
    esac
    if [ -n "$acct" ] && [ "$1" != auth ]; then
        GH_TOKEN=$(command gh auth token -u "$acct") command gh "$@"
    else
        command gh "$@"
    fi
}
