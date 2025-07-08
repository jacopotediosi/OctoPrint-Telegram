# Contribution Guidelines
This document outlines what you need to know before **[reporting bugs](#reporting-bugs)**
or **[creating pull requests](#creating-pull-requests)**.

This document is based on the [OctoPrint Contribution Guidelines](https://github.com/OctoPrint/OctoPrint/blob/master/CONTRIBUTING.md)
and inspired by the guide [How To Ask Questions The Smart Way](https://www.catb.org/~esr/faqs/smart-questions.html) by Eric S. Raymond and Rick Moen.

# Summary
* [Reporting bugs](#reporting-bugs)
  * [What should I do before submitting a bug report?](#what-should-i-do-before-submitting-a-bug-report)
  * [What should I pay attention to when writing a bug report?](#what-should-i-pay-attention-to-when-writing-a-bug-report)
* [Creating Pull Requests](#creating-pull-requests)

# Reporting bugs
If you encounter an issue with this plugin, you are welcome to [submit a bug report](https://github.com/jacopotediosi/OctoPrint-Telegram/issues/new/choose).

Before you do that for the first time though please take a moment to read the following sections _completely_ and also follow the instructions in the "new issue" form. Thank you! :smile:

### What should I do before submitting a bug report?
1. **Make sure you are in the right place.**
   This is the bug tracker for the [OctoPrint-Telegram](https://github.com/jacopotediosi/OctoPrint-Telegram) plugin.  
   Bugs related to other plugins or OctoPrint itself should not be reported here, unless they are caused by this plugin.
2. **Ensure you are using the latest version of the plugin**, to verify whether the issue you're experiencing has already been fixed.
3. **Search through the existing issues** (use GitHub's search feature) to check if the problem has already been reported.  
   Take your time to review potential duplicates carefully and be sure your issue is truly new.

### What should I pay attention to when writing a bug report?
1. **Choose a descriptive title.** Titles like "Please help" or "It doesn't work" are not descriptive.
   Summarize your problem in fewer than 100 characters.
2. **Clearly describe the issue in a reproducible way**, including all the steps necessary to reproduce it:
   - What actions did you take that led to the bug? What were you doing, or what was the printer doing at the time?
   - What unexpected behavior occurred, and what did you expect instead?
   - What is your environment? Please include:
     - OctoPrint version
     - OctoPrint-Telegram plugin version
     - OS and hardware (e.g., Raspberry Pi 4, RPi OS Lite)
     - Browser and browser version (for UI-related bugs)
     - Other installed OctoPrint plugins
   - Specifically mention any **non-standard setup** (e.g., running OctoPrint on Android, customized plugin settings).
   - If applicable, attach screenshots and/or videos that show the issue and the relevant plugin settings.
3. **Attach the logs captured during the occurrence of the bug.**
   Any issue without logs will be closed without a response, as it's not possible to help you without them.
   - If possible, enable debug-level logging and reproduce the bug again so the logs are as detailed as possible.
   - [Here](https://github.com/jacopotediosi/OctoPrint-Telegram/wiki/Where-are-the-logs%3F) is the documentation for this plugin’s logs.
   - [Here](https://community.octoprint.org/t/what-is-a-systeminfo-bundle-and-how-can-i-obtain-one/29887) is the documentation for OctoPrint logs.
   - [Here](https://webmasters.stackexchange.com/questions/8525/how-to-open-the-javascript-console-in-different-browsers) is how to access your browser’s JavaScript console.
4. **Never mix two or more issues in a single ticket.** If you encounter more than one bug, open a separate ticket for each.

# Creating Pull Requests
1. Create your pull request **from a custom branch** on your end (e.g. `improve/my-new-feature`). Pull requests created from a `master` branch will not be accepted.  
   The reason is that anything added to your PR's branch will become part of the PR itself.
   If you create a PR from your `master` branch, chances are high you'll accidentally include unrelated changes.
2. Create your pull request **only against the `devel` branch**. PRs targeting the `master` branch will not be accepted.
3. Create **one pull request per feature or bug fix**.
4. Make sure your pull request includes **only relevant changes**  
   Avoid modifications to unrelated files or addition of unnecessary files (e.g. your full virtual environment).  
   Ideally, your PR should consist of a single commit (use `git rebase` and `squash` to clean your history).
5. Ensure that your code **follows the current coding style**:
   - Use spaces for indentation, matching the existing style of the file you're editing
   - Use **English** for code, variable names, and comments
   - Add comments where needed to explain _why_ certain logic is applied
   - Stick to the plugin’s overall architecture and structure
   - **Do not include dead code**, such as commented-out experiments or unused variables
6. Install the **pre-commit hooks** with `pre-commit install` and run the full suite using:
   ```bash
   pre-commit run --all-files -v
   ```
