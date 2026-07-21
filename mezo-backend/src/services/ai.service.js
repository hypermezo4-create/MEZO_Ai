exports.generateText = async (prompt, model = 'MEZO-Custom-v1') => {
  // Bridge connector to mezo-ai-engine
  return {
    model,
    prompt,
    text: `استجابة محرك MEZO AI للطلب: "${prompt}". تم استخدام نموذج ${model}.`,
    usage: { prompt_tokens: 15, completion_tokens: 28, total_tokens: 43 }
  };
};
