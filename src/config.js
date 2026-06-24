import 'dotenv/config';

export const config = {
  googleAiKey:              process.env.GOOGLE_AI_KEY,
  agentModel:               process.env.AGENT_MODEL               || 'gemini-2.5-flash',
  agentMaxTokens:           parseInt(process.env.AGENT_MAX_TOKENS  || '1024'),
  googleServiceAccountPath: process.env.GOOGLE_SERVICE_ACCOUNT_PATH || './credentials/service_account.json',
  maxRows:                  parseInt(process.env.MAX_ROWS           || '10000'),
  port:                     parseInt(process.env.PORT               || '3000'),
};
