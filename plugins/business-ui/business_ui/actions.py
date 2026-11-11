"""Register typed Host actions."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from octop.infra.agents.plugins.host_contracts import PluginActor

from .models import (
    ActivationCompleteInput,
    ActivationDisconnectOutput,
    ActivationNativeInput,
    ActivationPatInput,
    ActivationStartOutput,
    ActivationStatusOutput,
    ClaimInput,
    ClaimOutput,
    ConnectionDeleteOutput,
    ConnectionIdInput,
    ConnectionListOutput,
    ConnectionSaveInput,
    ConnectionSaveOutput,
    ConnectionTestOutput,
    EmptyInput,
    InteractionRefInput,
    InteractionStateOutput,
    TicketIssueInput,
    TicketIssueOutput,
)
from .service import BusinessUiService


def register_actions(facade: Any) -> Sequence[tuple[str, type, type, Any, str, str]]:
    service = BusinessUiService(facade)

    async def connections_list(actor: PluginActor, _payload: EmptyInput) -> ConnectionListOutput:
        return await service.list_connections(actor)

    async def connections_save(
        actor: PluginActor, payload: ConnectionSaveInput
    ) -> ConnectionSaveOutput:
        return await service.save_connection(actor, payload)

    async def connections_delete(
        actor: PluginActor, payload: ConnectionIdInput
    ) -> ConnectionDeleteOutput:
        return await service.delete_connection(actor, payload)

    async def connections_test(
        actor: PluginActor, payload: ConnectionIdInput
    ) -> ConnectionTestOutput:
        return await service.test_connection(actor, payload)

    async def interactions_claim(actor: PluginActor, payload: ClaimInput) -> ClaimOutput:
        return await service.claim(actor, payload)

    async def interactions_get(
        actor: PluginActor, payload: InteractionRefInput
    ) -> InteractionStateOutput:
        return await service.get_interaction(actor, payload)

    async def interactions_cancel(
        actor: PluginActor, payload: InteractionRefInput
    ) -> InteractionStateOutput:
        return await service.cancel(actor, payload)

    async def tickets_issue(actor: PluginActor, payload: TicketIssueInput) -> TicketIssueOutput:
        return await service.issue_ticket(actor, payload)

    async def activations_start(
        actor: PluginActor, payload: ConnectionIdInput
    ) -> ActivationStartOutput:
        return await service.start_activation(actor, payload)

    async def activations_complete(
        actor: PluginActor, payload: ActivationCompleteInput
    ) -> ActivationStatusOutput:
        return await service.complete_activation(actor, payload)

    async def activations_native(
        actor: PluginActor, payload: ActivationNativeInput
    ) -> ActivationStatusOutput:
        return await service.native_activation(actor, payload)

    async def activations_pat(
        actor: PluginActor, payload: ActivationPatInput
    ) -> ActivationStatusOutput:
        return await service.pat_activation(actor, payload)

    async def activations_disconnect(
        actor: PluginActor, payload: ConnectionIdInput
    ) -> ActivationDisconnectOutput:
        return await service.disconnect_activation(actor, payload)

    return (
        (
            "connections.list",
            EmptyInput,
            ConnectionListOutput,
            connections_list,
            "List connections",
            "authenticated",
        ),
        (
            "connections.save",
            ConnectionSaveInput,
            ConnectionSaveOutput,
            connections_save,
            "Save connection",
            "admin",
        ),
        (
            "connections.delete",
            ConnectionIdInput,
            ConnectionDeleteOutput,
            connections_delete,
            "Delete connection",
            "admin",
        ),
        (
            "connections.test",
            ConnectionIdInput,
            ConnectionTestOutput,
            connections_test,
            "Test connection handshake",
            "admin",
        ),
        (
            "interactions.claim",
            ClaimInput,
            ClaimOutput,
            interactions_claim,
            "Claim draft interaction",
            "authenticated",
        ),
        (
            "interactions.get",
            InteractionRefInput,
            InteractionStateOutput,
            interactions_get,
            "Fetch authoritative interaction",
            "authenticated",
        ),
        (
            "interactions.cancel",
            InteractionRefInput,
            InteractionStateOutput,
            interactions_cancel,
            "Cancel draft interaction",
            "authenticated",
        ),
        (
            "tickets.issue",
            TicketIssueInput,
            TicketIssueOutput,
            tickets_issue,
            "Issue one-time page ticket",
            "authenticated",
        ),
        (
            "activations.start",
            ConnectionIdInput,
            ActivationStartOutput,
            activations_start,
            "Start per-user activation",
            "authenticated",
        ),
        (
            "activations.complete",
            ActivationCompleteInput,
            ActivationStatusOutput,
            activations_complete,
            "Complete OAuth2 activation",
            "authenticated",
        ),
        (
            "activations.native",
            ActivationNativeInput,
            ActivationStatusOutput,
            activations_native,
            "Activate with native account login",
            "authenticated",
        ),
        (
            "activations.pat",
            ActivationPatInput,
            ActivationStatusOutput,
            activations_pat,
            "Activate with a personal access token",
            "authenticated",
        ),
        (
            "activations.disconnect",
            ConnectionIdInput,
            ActivationDisconnectOutput,
            activations_disconnect,
            "Revoke this user's activation",
            "authenticated",
        ),
    )
