from __future__ import annotations

import asyncio
import logging
import traceback

import hikari
import lightbulb
from etc.perms_str import get_perm_str
import datetime
from models import SnedContext
from models.errors import RoleHierarchyError
from utils import helpers
import typing as t

if t.TYPE_CHECKING:
    from models.bot import SnedBot

logger = logging.getLogger(__name__)

eh = lightbulb.Plugin("Error-Handler")


async def log_error_to_homeguild(
    error_str: str, ctx: t.Optional[lightbulb.Context] = None, event: t.Optional[hikari.Event] = None
) -> None:

    error_lines = error_str.split("\n")
    paginator = lightbulb.utils.StringPaginator(max_chars=2000, prefix="```py\n", suffix="```")

    if ctx:
        paginator.add_line(
            f"Error in '{ctx.get_guild().name}' ({ctx.guild_id}) during command '{ctx.command.name}' executed by user '{ctx.author}' ({ctx.author.id})\n"
        )

    elif event:
        paginator.add_line(f"Ignoring exception in listener for {event.__class__.__name__}:\n")
    else:
        paginator.add_line(f"Uncaught exception:")

    for line in error_lines:
        paginator.add_line(line)

    channel_id = ctx.app.config.get("error_logging_channel")

    if not channel_id:
        return

    for page in paginator.build_pages():
        try:
            await ctx.app.rest.create_message(channel_id, page)
        except Exception as error:
            logging.error(f"Failed sending traceback to logging channel: {error}")


async def application_error_handler(ctx: SnedContext, error: lightbulb.LightbulbError) -> None:
    if isinstance(error, lightbulb.CheckFailure):

        if isinstance(error, lightbulb.MissingRequiredPermission):
            embed = hikari.Embed(
                title="❌ Missing Permissions",
                description=f"You require `{get_perm_str(error.missing_perms)}` permissions to execute this command.",
                color=ctx.app.error_color,
            )
            return await ctx.respond(embed=embed, flags=hikari.MessageFlag.EPHEMERAL)
        elif isinstance(error, lightbulb.BotMissingRequiredPermission):
            embed = hikari.Embed(
                title="❌ Bot Missing Permissions",
                description=f"The bot requires `{get_perm_str(error.missing_perms)}` permissions to execute this command.",
                color=ctx.app.error_color,
            )
            return await ctx.respond(embed=embed, flags=hikari.MessageFlag.EPHEMERAL)
    elif isinstance(error, lightbulb.CommandIsOnCooldown):
        embed = hikari.Embed(
            title="🕘 Cooldown Pending",
            description=f"Please retry in: `{datetime.timedelta(seconds=round(error.retry_after))}`",
            color=ctx.app.error_color,
        )
        return await ctx.respond(embed=embed, flags=hikari.MessageFlag.EPHEMERAL)
    elif isinstance(error, lightbulb.CommandInvocationError):

        if isinstance(error.original, asyncio.TimeoutError):
            embed = hikari.Embed(
                title="❌ Action timed out",
                description=f"This command timed out.",
                color=ctx.app.error_color,
            )
            return await ctx.respond(embed=embed, flags=hikari.MessageFlag.EPHEMERAL)
        elif isinstance(error.original, hikari.InternalServerError):
            embed = hikari.Embed(
                title="❌ Discord Server Error",
                description="This action has failed due to an issue with Discord's servers. Please try again in a few moments.",
                color=ctx.app.error_color,
            )
            return await ctx.respond(embed=embed, flags=hikari.MessageFlag.EPHEMERAL)
        elif isinstance(error.original, hikari.ForbiddenError):
            embed = hikari.Embed(
                title="❌ Forbidden",
                description=f"This action has failed due to a lack of permissions.\n**Error:** {error}",
                color=ctx.app.error_color,
            )
        elif isinstance(error.original, RoleHierarchyError):
            embed = hikari.Embed(
                title="❌ Role Hiearchy Error",
                description=f"This action failed due to trying to modify a user with a role higher than the bot's highest role.",
                color=ctx.app.error_color,
            )
            return await ctx.respond(embed=embed, flags=hikari.MessageFlag.EPHEMERAL)

    logging.error("Ignoring exception in command {}:".format(ctx.command.name))
    exception_msg = "\n".join(traceback.format_exception(type(error), error, error.__traceback__))
    logging.error(exception_msg)
    error = error.original if hasattr(error, "original") else error

    embed = hikari.Embed(
        title="❌ Unhandled exception",
        description=f"An error happened that should not have happened. Please [contact us](https://discord.gg/KNKr8FPmJa) with a screenshot of this message!\n**Error:** ```{error.__class__.__name__}: {error}```",
        color=ctx.app.error_color,
    )
    embed.set_footer(text=f"Guild: {ctx.guild_id}")
    await log_error_to_homeguild(exception_msg, ctx)

    await ctx.respond(embed=embed, flags=hikari.MessageFlag.EPHEMERAL)


@eh.listener(lightbulb.SlashCommandErrorEvent)
async def slash_error_handler(event: lightbulb.SlashCommandErrorEvent) -> None:
    await application_error_handler(event.context, event.exception)


@eh.listener(lightbulb.MessageCommandErrorEvent)
async def message_error_handler(event: lightbulb.MessageCommandErrorEvent) -> None:
    await application_error_handler(event.context, event.exception)


@eh.listener(lightbulb.UserCommandErrorEvent)
async def user_error_handler(event: lightbulb.UserCommandErrorEvent) -> None:
    await application_error_handler(event.context, event.exception)


@eh.listener(lightbulb.PrefixCommandErrorEvent)
async def prefix_error_handler(event: lightbulb.PrefixCommandErrorEvent) -> None:
    if isinstance(event.exception, lightbulb.CheckFailure):
        return

    error = event.exception.original if hasattr(event.exception, "original") else event.exception

    embed = hikari.Embed(
        title="❌ Exception encountered",
        description=f"```{error}```",
        color=event.context.app.error_color,
    )
    await event.context.respond(embed=embed)
    raise event.exception


def load(bot: SnedBot) -> None:
    bot.add_plugin(eh)


def unload(bot: SnedBot) -> None:
    bot.remove_plugin(eh)
