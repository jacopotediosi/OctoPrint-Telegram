class Formatters:
    """Static formatting utilities for various data types."""

    @staticmethod
    def format_size(bytes_value) -> str:
        """
        Format file size in human readable format.
        From octoprint/static/js/app/helpers.js transferred to python.

        Args:
            bytes_value: Size in bytes

        Returns:
            Formatted size string (e.g., "1.2 MB", "500 bytes")
        """
        if not bytes_value:
            return "-"

        bytes_value = float(bytes_value)
        units = ["bytes", "KB", "MB", "GB"]

        for i in range(len(units)):
            if bytes_value < 1024:
                return f"{bytes_value:3.1f} {units[i]}"
            bytes_value = bytes_value / 1024

        return f"{bytes_value:.1f}TB"

    @staticmethod
    def format_filament(filament) -> str:
        """
        Format filament usage information.
        From octoprint/static/js/app/helpers.js transferred to python.

        Args:
            filament: Dict containing 'length' and optionally 'volume'

        Returns:
            Formatted filament string (e.g., "12.34 m / 5.67 cm^3")
        """

        if not filament or "length" not in filament:
            return "-"

        result = f"{float(filament['length']) / 1000:.02f} m"

        if "volume" in filament and filament["volume"]:
            result += f" / {float(filament['volume']):.02f} cm^3"

        return result

    @staticmethod
    def format_duration(seconds) -> str:
        """
        Format duration in HH:MM:SS format.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted duration string (e.g., "02:30:45")
        """
        if seconds is None:
            return "-"

        if seconds < 1:
            return "00:00:00"

        s = int(seconds) % 60
        m = (int(seconds) % 3600) / 60
        h = int(seconds) / 3600

        return "%02d:%02d:%02d" % (h, m, s)

    @staticmethod
    def format_fuzzy_print_time(total_seconds):
        """
        Formats a print time estimate in a very fuzzy way.
        From octoprint/static/js/app/helpers.js transferred to python.

        Accuracy decreases as the estimation gets higher:
        * less than 30s: "a few seconds"
        * 30s to a minute: "less than a minute"
        * 1 to 30min: rounded to full minutes, above 30s is minute + 1 ("27 minutes", "2 minutes")
        * 30min to 40min: "40 minutes"
        * 40min to 50min: "50 minutes"
        * 50min to 1h: "1 hour"
        * 1 to 12h: rounded to half hours, 15min to 45min is ".5", above that hour + 1 ("4 hours", "2.5 hours")
        * 12 to 24h: rounded to full hours, above 30min is hour + 1, over 23.5h is "1 day"
        * Over a day: rounded to half days, 8h to 16h is ".5", above that days + 1 ("1 day", "4 days", "2.5 days")

        Args:
            total_seconds: Time in seconds

        Returns:
            Fuzzy time string (e.g., "2.5 hours", "3 days")
        """

        if not total_seconds or total_seconds < 1:
            return "-"

        seconds = int(total_seconds)
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)

        replacements = {
            "days": days,
            "hours": hours,
            "minutes": minutes,
            "seconds": seconds,
            "totalSeconds": total_seconds,
        }

        text = "-"

        if days >= 1:
            # Days
            if hours >= 16:
                replacements["days"] += 1
                if replacements["days"] == 1:
                    text = "%(days)d day"
                else:
                    text = "%(days)d days"
            elif 8 <= hours < 16:
                text = "%(days)d.5 days"
            else:
                if days == 1:
                    text = "%(days)d day"
                else:
                    text = "%(days)d days"
        elif hours >= 1:
            # Only hours
            if hours < 12:
                if minutes < 15:
                    # Less than .15 => .0
                    if hours == 1:
                        text = "%(hours)d hour"
                    else:
                        text = "%(hours)d hours"
                elif 15 <= minutes < 45:
                    # Between .25 and .75 => .5
                    text = "%(hours)d.5 hours"
                else:
                    # Over .75 => hours + 1
                    replacements["hours"] += 1
                    if replacements["hours"] == 1:
                        text = "%(hours)d hour"
                    else:
                        text = "%(hours)d hours"
            else:
                if hours == 23 and minutes > 30:
                    # Over 23.5 hours => 1 day
                    text = "1 day"
                else:
                    if minutes > 30:
                        # Over .5 => hours + 1
                        replacements["hours"] += 1
                    text = "%(hours)d hours"
        elif minutes >= 1:
            # Only minutes
            if minutes < 2:
                if seconds < 30:
                    text = "a minute"
                else:
                    text = "2 minutes"
            elif minutes < 30:
                if seconds > 30:
                    replacements["minutes"] += 1
                text = "%(minutes)d minutes"
            elif minutes <= 40:
                text = "40 minutes"
            elif minutes <= 50:
                text = "50 minutes"
            else:
                text = "1 hour"
        else:
            # Only seconds
            if seconds < 30:
                text = "a few seconds"
            else:
                text = "less than a minute"

        return text % replacements
