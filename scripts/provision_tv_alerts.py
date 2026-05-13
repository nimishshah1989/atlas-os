"""Run nightly at 19:00 IST to sync TV alerts with Atlas universe."""

from atlas.signals.provisioner import provision_tv_alerts

if __name__ == "__main__":
    result = provision_tv_alerts()
    print(f"Provisioning complete: {result}")
