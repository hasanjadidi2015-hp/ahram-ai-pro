try:

    from win11toast import toast

    _available = True

except Exception as e:

    print("DESKTOP NOTIFICATION SETUP WARNING:", e)
    _available = False


def send_desktop_notification(title, message):

    if not _available:

        print("DESKTOP NOTIFICATION SKIPPED (win11toast not available)")
        return

    try:

        toast(title, message)

    except Exception as e:

        print("DESKTOP NOTIFICATION ERROR:", e)


if __name__ == "__main__":

    send_desktop_notification(
        "تست ایجنت اهرم",
        "این یک اعلان تستی روی کامپیوتر است"
    )