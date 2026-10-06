import {
  axios,
  buildHeaders,
  buildOpenAIHeaders,
  isOpenAIChatCompletionsUrl,
  proxyEcnuChatCompletionsUrl,
} from "../core";

export function createChatApi() {
  return {
    async chat(payload, settings) {
      if (isOpenAIChatCompletionsUrl(settings.backend_url)) {
        const historyMessages = Array.isArray(payload.history)
          ? payload.history.map((item) => ({ role: item.role, content: item.content }))
          : [];
        const messages = payload.system_prompt
          ? [{ role: "system", content: payload.system_prompt }, ...historyMessages]
          : historyMessages;

        const res = await axios.post(
          proxyEcnuChatCompletionsUrl(settings.backend_url),
          {
            model: payload.model,
            messages,
            temperature: payload.temperature,
            top_p: payload.top_p,
            max_tokens: payload.max_tokens,
          },
          {
            headers: buildOpenAIHeaders(settings),
          },
        );

        return {
          response: res.data?.choices?.[0]?.message?.content ?? "",
          tokens_used: res.data?.usage?.total_tokens,
        };
      }

      const res = await axios.post(`${settings.backend_url}/chat`, payload, {
        headers: buildHeaders(settings),
      });
      return res.data;
    },
  };
}
