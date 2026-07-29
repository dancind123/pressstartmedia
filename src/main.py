from pressstart_media.agent import MediaAgent
from pressstart_media.display import Display
from pressstart_media.manager import MediaManager


def main() -> None:
    agent = MediaAgent()
    startup_display = Display()

    try:
        startup_display.show_status(
            "Starting Press Start Media",
            f"Player ID\n{agent.player_id}",
        )

        agent.connect()

        if not agent.is_provisioned():
            startup_display.show_status(
                "Waiting for Home Assistant",
                (
                    "This player is ready for provisioning.\n"
                    f"Player ID\n{agent.player_id}"
                ),
            )

            agent.wait_for_provisioning()

            startup_display.show_status(
                "Provisioning Complete",
                "Loading player configuration...",
            )

        startup_display.hide_logo()

        manager = MediaManager(
            state_callback=agent.publish_runtime_state,
        )

        agent.set_command_handler(
            manager.handle_command
        )

        manager.run()

    finally:
        startup_display.hide_logo()
        agent.disconnect()


if __name__ == "__main__":
    main()
