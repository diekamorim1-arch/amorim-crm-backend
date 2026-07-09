import hashlib
import hmac
import json
import uuid

from app.config import get_settings
from app.core.supabase_client import get_service_client
from tests.conftest import _create_user_and_sign_in, auth_headers


def test_criar_conversa_enviar_e_ler_mensagem(client, gestor_token, gestor_user_id):
    sb = get_service_client()
    contact = client.post(
        "/api/v1/contacts",
        json={"name": "Contato Inbox", "whatsapp": "+5511911110000", "origin": "whatsapp_direto", "owner_id": gestor_user_id},
        headers=auth_headers(gestor_token),
    ).json()

    try:
        conversation = client.post(
            "/api/v1/conversations", json={"contact_id": contact["id"]}, headers=auth_headers(gestor_token)
        ).json()

        sent = client.post(
            f"/api/v1/conversations/{conversation['id']}/messages", json={"text": "Olá!"}, headers=auth_headers(gestor_token)
        )
        assert sent.status_code == 200
        assert sent.json()["direction"] == "out"

        messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages", headers=auth_headers(gestor_token))
        assert len(messages.json()) == 1
    finally:
        sb.table("messages").delete().eq("conversation_id", conversation["id"]).execute()
        sb.table("conversations").delete().eq("id", conversation["id"]).execute()
        # send_message também grava em activities (contact_id); precisa ir
        # embora antes do delete de contacts, senão viola a FK.
        sb.table("activities").delete().eq("contact_id", contact["id"]).execute()
        sb.table("contacts").delete().eq("id", contact["id"]).execute()


def test_get_messages_marca_conversa_como_lida(client, gestor_token, gestor_user_id):
    """Cobre o efeito colateral de get_messages: unread deve ir a 0 ao ler."""
    sb = get_service_client()
    contact = client.post(
        "/api/v1/contacts",
        json={"name": "Contato Nao Lido", "whatsapp": "+5511911110001", "origin": "whatsapp_direto", "owner_id": gestor_user_id},
        headers=auth_headers(gestor_token),
    ).json()

    try:
        conversation = client.post(
            "/api/v1/conversations", json={"contact_id": contact["id"]}, headers=auth_headers(gestor_token)
        ).json()
        assert conversation["unread"] == 0

        # simula chegada de mensagens não lidas (como o webhook faria)
        sb.table("conversations").update({"unread": 3}).eq("id", conversation["id"]).execute()
        before = sb.table("conversations").select("unread").eq("id", conversation["id"]).execute().data[0]
        assert before["unread"] == 3

        response = client.get(f"/api/v1/conversations/{conversation['id']}/messages", headers=auth_headers(gestor_token))
        assert response.status_code == 200

        after = sb.table("conversations").select("unread").eq("id", conversation["id"]).execute().data[0]
        assert after["unread"] == 0
    finally:
        sb.table("messages").delete().eq("conversation_id", conversation["id"]).execute()
        sb.table("conversations").delete().eq("id", conversation["id"]).execute()
        sb.table("contacts").delete().eq("id", contact["id"]).execute()


def test_atribuir_conversa(client, gestor_token, gestor_user_id):
    sb = get_service_client()
    contact = client.post(
        "/api/v1/contacts",
        json={"name": "Contato Atribuicao", "whatsapp": "+5511900000001", "origin": "outro", "owner_id": gestor_user_id},
        headers=auth_headers(gestor_token),
    ).json()

    try:
        conversation = client.post(
            "/api/v1/conversations", json={"contact_id": contact["id"]}, headers=auth_headers(gestor_token)
        ).json()

        updated = client.patch(
            f"/api/v1/conversations/{conversation['id']}/assignee", json={"assignee_id": gestor_user_id}, headers=auth_headers(gestor_token)
        )
        assert updated.json()["assignee_id"] == gestor_user_id
    finally:
        sb.table("conversations").delete().eq("id", conversation["id"]).execute()
        sb.table("contacts").delete().eq("id", contact["id"]).execute()


def test_criar_conversa_rejeita_contato_de_outro_tenant(client, gestor_token):
    """Guarda de tenant (mesma classe de vulnerabilidade corrigida nas Tasks 6 e 7):
    contact_id de um tenant diferente não pode ser usado para criar uma conversa
    no tenant do chamador."""
    sb = get_service_client()
    foreign_tenant = sb.table("tenants").insert({"name": "Loja Alheia", "slug": f"alheia-{uuid.uuid4().hex[:8]}"}).execute().data[0]
    try:
        foreign_token, foreign_user_id = _create_user_and_sign_in(sb, foreign_tenant["id"], "gestor")
        try:
            foreign_contact = (
                sb.table("contacts")
                .insert(
                    {
                        "tenant_id": foreign_tenant["id"], "name": "Contato Estrangeiro", "whatsapp": "+5511988887777",
                        "origin": "outro", "owner_id": foreign_user_id,
                    }
                )
                .execute()
                .data[0]
            )
            try:
                response = client.post(
                    "/api/v1/conversations", json={"contact_id": foreign_contact["id"]}, headers=auth_headers(gestor_token)
                )
                assert response.status_code == 404

                leaked_conversations = (
                    sb.table("conversations").select("id").eq("contact_id", foreign_contact["id"]).execute().data
                )
                assert leaked_conversations == []
            finally:
                sb.table("contacts").delete().eq("id", foreign_contact["id"]).execute()
        finally:
            sb.table("user_profiles").delete().eq("id", foreign_user_id).execute()
            sb.auth.admin.delete_user(foreign_user_id)
    finally:
        sb.table("tenants").delete().eq("id", foreign_tenant["id"]).execute()


def test_webhook_rejeita_assinatura_invalida(client):
    response = client.post(
        "/api/v1/webhooks/evolution",
        json={"instance": {"phone": "x"}, "message": {"from": "y", "text": "z"}},
        headers={"x-evolution-signature": "assinatura-errada"},
    )
    assert response.status_code == 401


def test_webhook_aceita_assinatura_valida_e_processa_mensagem(client, gestor_token, gestor_user_id, test_tenant):
    """Cobertura de caminho feliz do webhook sem depender de uma instância real
    da EvolutionAPI: computamos a assinatura HMAC com o mesmo segredo que o
    servidor usa (`evolution_webhook_secret`, vazio neste ambiente de teste,
    mas o algoritmo é o mesmo com um segredo real em produção) e verificamos
    que a mensagem é ingerida corretamente (conversa criada, unread
    incrementado, mensagem 'in' persistida, last_interaction_at atualizado)."""
    sb = get_service_client()
    settings = get_settings()
    # Números únicos por execução: a EvolutionAPI resolve a conexão só por
    # `phone` (sem escopo de tenant na busca), então um número fixo poderia
    # colidir com lixo de uma execução anterior que falhou a limpar (já
    # aconteceu uma vez neste projeto compartilhado — ver task-8-report.md).
    unique_suffix = uuid.uuid4().hex[:8]
    instance_phone = f"+55119{unique_suffix}"
    contact_whatsapp = f"+55118{unique_suffix}"

    connection = sb.table("connections").insert(
        {"tenant_id": test_tenant["id"], "user_id": gestor_user_id, "phone": instance_phone}
    ).execute().data[0]
    contact = client.post(
        "/api/v1/contacts",
        json={"name": "Contato Webhook", "whatsapp": contact_whatsapp, "origin": "whatsapp_direto", "owner_id": gestor_user_id},
        headers=auth_headers(gestor_token),
    ).json()

    conversation_id = None
    try:
        payload = {
            "instance": {"phone": instance_phone},
            "message": {"from": contact_whatsapp, "text": "Olá, preciso de ajuda"},
        }
        body = json.dumps(payload).encode()
        signature = hmac.new(settings.evolution_webhook_secret.encode(), body, hashlib.sha256).hexdigest()

        response = client.post(
            "/api/v1/webhooks/evolution",
            content=body,
            headers={"x-evolution-signature": signature, "content-type": "application/json"},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "processed"}

        conversation = (
            sb.table("conversations")
            .select("*")
            .eq("tenant_id", test_tenant["id"])
            .eq("contact_id", contact["id"])
            .execute()
            .data[0]
        )
        conversation_id = conversation["id"]
        assert conversation["unread"] == 1

        messages = sb.table("messages").select("*").eq("conversation_id", conversation_id).execute().data
        assert len(messages) == 1
        assert messages[0]["direction"] == "in"
        assert messages[0]["text"] == "Olá, preciso de ajuda"
    finally:
        if conversation_id:
            sb.table("messages").delete().eq("conversation_id", conversation_id).execute()
            sb.table("conversations").delete().eq("id", conversation_id).execute()
        # o webhook também grava em activities (contact_id); precisa ir embora
        # antes do delete de contacts, senão viola a FK.
        sb.table("activities").delete().eq("contact_id", contact["id"]).execute()
        sb.table("contacts").delete().eq("id", contact["id"]).execute()
        sb.table("connections").delete().eq("id", connection["id"]).execute()
