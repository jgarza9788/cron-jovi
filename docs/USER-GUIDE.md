# Cron Jovi user guide

Cron Jovi does things for you on your computer: when something happens, it runs
a list of steps. No coding needed, and nothing leaves your computer.

## Your first workflow

1. Open **Cron Jovi** from your app launcher.
2. Press **New** and pick an idea, like Water Reminder.
3. Look over its steps. Starter ideas arrive switched off, so nothing happens yet.
4. Press **Run** to try it, then flip the switch at the top to **On**.

Changes save by themselves. If you make a mistake, press the undo arrow.

## Describing it

Each workflow has a **Description** box above its trigger. Use it for notes on
what the workflow does and why, as long as you like. It's blank until you fill
it in, and it's included when you share the workflow.

## When it runs

Press **Add a trigger** and choose:

- **A hotkey**: press the keys you want. The first time, Cron Jovi asks to switch hotkeys on.
- **A schedule**: every day, every weekday, every few hours, and so on.
- **A file changes**: for example, something new lands in Downloads.
- **A device is plugged in**: a USB drive, or a specific one by name.
- **The battery runs low**, or **power is plugged or unplugged**. Laptops only.
- **You log in**, or **the computer wakes from sleep**.
- **A web request arrives**: for people who write scripts.

With no trigger, a workflow runs only when you press Run.

## What it does

Click an action on the right to add it, or drag it where you want. Drag a step
by its dots to move it, or use its **⋯** menu. Click a step to open its options.

- **If / Otherwise** does different things depending on, say, the time of day.
  Add more conditions when several things must all be true.
- **Repeat** does steps a set number of times, once for each item in a list, or
  once for each part of some text, like `one,two,three` split at the commas.
  The number can come from a variable: use the tag button next to it.
- **Calculate** does sums, including with saved values.
- **Ask a Question** pops up a box and waits for your answer.
- **Run Another Workflow** uses one workflow as a step in another.
- **If something goes wrong** holds steps that run only after a failure.

One step can pass something to the next: open **More options**, fill in
**Remember the result as**, then use the tag button on a later step to insert it.

## When the computer was off

Scheduled workflows ask what to do if the computer was asleep or off:

- **Run once when the computer is back.** Missing five days still means one run.
- **Skip it.** Wait for the next time.

They also ask what to do if the last run hasn't finished yet.

## Taking a break

**Overview** shows what's coming up and anything that needs your attention. To
stop everything for a while, turn on **Pause everything** in Settings. You can
still press Run, and nothing catches up when you resume.

To turn off one step without deleting it, open its **⋯** menu.

## Did it work?

Open a workflow's **History** tab, or **Run log** for everything. Every run has a
row, even skipped ones, and failed runs show exactly what went wrong. If a
workflow fails while you aren't watching, you get a notification.

## Something says "not found"

Some steps need a small Linux tool. The bar at the bottom of the window flags
anything missing: click it to see how to install it.

## Shared workflows

Open **Gallery** to add a folder or a web address of shared workflows, or use
**Import** in Settings for a single file. Cron Jovi shows you what a workflow would
do before adding it, and it arrives switched off.

**Only add workflows from people you trust.** A workflow can do anything you can
do on your computer. If you see commands you don't understand, don't add it.

## Removing Cron Jovi

Run `./uninstall.sh` in its folder. Your workflows and history stay, unless you
run `./uninstall.sh --purge`.
