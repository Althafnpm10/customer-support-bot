(function () {
  function randomId(prefix) {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return prefix + "_" + window.crypto.randomUUID().replace(/-/g, "").slice(0, 10);
    }
    return prefix + "_" + Math.random().toString(36).slice(2, 12);
  }

  class FrontendBackendChatPlugin {
    constructor(options) {
      const config = options || {};
      this.apiBase = config.apiBase || "";
      this.storagePrefix = config.storagePrefix || "cu_support";
      this.userIdKey = this.storagePrefix + "_user_id";
      this.conversationIdKey = this.storagePrefix + "_conversation_id";
      this.userId = this.getOrCreateUserId();
      this.conversationId = this.getConversationId();
    }

    getOrCreateUserId() {
      const existing = window.localStorage.getItem(this.userIdKey);
      if (existing) {
        return existing;
      }
      const generated = randomId("user");
      window.localStorage.setItem(this.userIdKey, generated);
      return generated;
    }

    getConversationId() {
      return window.localStorage.getItem(this.conversationIdKey);
    }

    async resetConversation() {
      const currentConversationId = this.conversationId || this.getConversationId();
      this.conversationId = null;
      window.localStorage.removeItem(this.conversationIdKey);

      if (currentConversationId) {
        try {
          await fetch(this.apiBase + "/conversations/" + encodeURIComponent(currentConversationId), {
            method: "DELETE",
          });
        } catch (error) {
          // Reset local session even if backend delete fails.
        }
      }
    }

    async sendMessage(message) {
      const payload = {
        message: message,
        user_id: this.userId,
      };
      if (this.conversationId) {
        payload.conversation_id = this.conversationId;
      }

      const response = await fetch(this.apiBase + "/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        let detail = "Unable to contact support backend.";
        try {
          const data = await response.json();
          if (data && data.error) {
            detail = data.error;
          }
        } catch (error) {
          detail = "Unable to contact support backend.";
        }
        throw new Error(detail);
      }

      const data = await response.json();
      if (data.conversation_id) {
        this.conversationId = data.conversation_id;
        window.localStorage.setItem(this.conversationIdKey, this.conversationId);
      }
      return data;
    }
  }

  window.FrontendBackendChatPlugin = FrontendBackendChatPlugin;
})();
