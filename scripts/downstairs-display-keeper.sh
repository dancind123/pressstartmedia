#!/bin/bash

export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export WAYLAND_DISPLAY="wayland-0"

# Allow Labwc to finish establishing its initial output layout before
# enforcing the permanent Downstairs Bar display configuration.
sleep 5
last_signature=""

get_output_for_display() {
    local make="$1"
    local model="$2"

    wlr-randr 2>/dev/null | awk \
        -v wanted_make="$make" \
        -v wanted_model="$model" '
        /^[^ ]/ {
            output=$1
            make=""
            model=""
        }

        /^  Make:/ {
            sub(/^  Make: /, "")
            make=$0
        }

        /^  Model:/ {
            sub(/^  Model: /, "")
            model=$0

            if (make == wanted_make && model == wanted_model) {
                print output
                exit
            }
        }
    '
}

while true; do
    snapshot="$(wlr-randr 2>/dev/null || true)"

    sceptre_output="$(
        get_output_for_display \
            "Sceptre Tech Inc" \
            "Sceptre H32"
    )"

    lg_output="$(
        get_output_for_display \
            "LG Electronics" \
            "LG TV"
    )"

    identity_state="SCEPTRE=${sceptre_output:-OFF};LG=${lg_output:-OFF}"

    if [ -n "$sceptre_output" ] && [ -n "$lg_output" ]; then
        desired_state="${identity_state};SCEPTRE_POS=0,0;LG_POS=1080,0"
    elif [ -n "$sceptre_output" ]; then
        desired_state="${identity_state};SCEPTRE_POS=0,0"
    elif [ -n "$lg_output" ]; then
        desired_state="${identity_state};LG_POS=0,0"
    else
        desired_state="${identity_state};NONE"
    fi

    signature="$(
        printf '%s' "$snapshot" |
            sha256sum |
            awk '{print $1}'
    )"

    signature="${signature}:${desired_state}"

    if [ "$signature" != "$last_signature" ]; then
        if [ -n "$sceptre_output" ]; then
            wlr-randr \
                --output "$sceptre_output" \
                --mode 1920x1080@60.000000Hz \
                --transform 90 \
                --pos 0,0 \
                >/dev/null 2>&1 || true
        fi

        if [ -n "$lg_output" ]; then
            if [ -n "$sceptre_output" ]; then
                lg_position="1080,0"
            else
                lg_position="0,0"
            fi

            wlr-randr \
                --output "$lg_output" \
                --mode 1920x1080@60.000000Hz \
                --transform 270 \
                --pos "$lg_position" \
                >/dev/null 2>&1 || true
        fi

        snapshot="$(wlr-randr 2>/dev/null || true)"

        last_signature="$(
            printf '%s' "$snapshot" |
                sha256sum |
                awk '{print $1}'
        ):${desired_state}"
    fi

    sleep 2
done