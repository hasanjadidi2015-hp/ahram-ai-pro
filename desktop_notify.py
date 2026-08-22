try:

    from win11toast import toast

    _available = True

except Exception as e:

    print("DESKTOP NOTIFICATION SETUP WARNING:", e)
    _available = False


def send_desktop_notification(title, message):

    if not _available:

        print("DESKTOP NOTIFICATION SKIPPED (win11toast not available)")
        return False

    try:
        # win11toast گاهی یه دیکشنری دیباگ داخلی (مثل {'arguments': ...}) روی
        # stdout چاپ می‌کنه که ربطی به لاگ ما نداره؛ خفه‌ش می‌کنیم که لاگ تمیز بمونه.
        import io
        import contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            toast(title, message)
        return True

    except Exception as e:

        print("DESKTOP NOTIFICATION ERROR:", e)
        return False


if __name__ == "__main__":

    send_desktop_notification(
        "تست ایجنت اهرم",
        "این یک اعلان تستی روی کامپیوتر است"
    )