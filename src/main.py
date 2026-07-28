from pressstart_media.agent import MediaAgent
from pressstart_media.manager import MediaManager


def main() -> None:
    agent = MediaAgent()

    manager = MediaManager(
        state_callback=agent.publish_runtime_state,
    )

    agent.set_command_handler(
        manager.handle_command
    )

    try:
        agent.connect()
        manager.run()

    finally:
        agent.disconnect()


if __name__ == "__main__":
    main()
