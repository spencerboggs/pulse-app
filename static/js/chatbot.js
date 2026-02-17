// ============================================================
// CHATBOT MESSAGE PARSING AND CONTEXT HANDLING
// ============================================================

// Chat state management - will be extended with backend integration
const chatState = {
  messages: [],
  context: {
    currentTopic: null,
    userPreferences: {},
    conversationHistory: []
  }
};

// Initialize chat interface
document.addEventListener('DOMContentLoaded', () => {
  const chatInput = document.getElementById('chatInput');
  const sendButton = document.getElementById('sendButton');
  const chatMessages = document.getElementById('chatMessages');

  // Send message on button click
  sendButton.addEventListener('click', handleSendMessage);

  // Send message on Enter key
  chatInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
      handleSendMessage();
    }
  });

  // Parse user message and extract intent/keywords
  function handleSendMessage() {
    const messageText = chatInput.value.trim();
    if (!messageText) return;

    // Add user message to chat
    addMessageToChat(messageText, 'user');
    
    // Parse message for context and intent
    const parsedMessage = parseMessage(messageText);
    
    // Update conversation context
    updateContext(parsedMessage);
    
    // Generate response based on parsed message
    const response = generateResponse(parsedMessage);
    
    // Simulate typing delay for bot response
    setTimeout(() => {
      addMessageToChat(response, 'bot');
    }, 500);

    // Clear input
    chatInput.value = '';
  }

  // Add message to chat UI
  function addMessageToChat(text, sender) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${sender}-message`;
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = sender === 'bot' ? 'P' : 'You';
    
    const content = document.createElement('div');
    content.className = 'message-content';
    
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.textContent = text;
    
    const time = document.createElement('div');
    time.className = 'message-time';
    time.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    
    content.appendChild(bubble);
    content.appendChild(time);
    messageDiv.appendChild(avatar);
    messageDiv.appendChild(content);
    
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    // Store in chat state
    chatState.messages.push({ text, sender, timestamp: new Date() });
  }

  // Parse user message to extract intent, keywords, and context
  function parseMessage(message) {
    const lowerMessage = message.toLowerCase();
    
    // Intent detection - categorize user's intent
    const intents = {
      music: ['music', 'song', 'artist', 'album', 'genre', 'listen', 'playlist', 'spotify'],
      events: ['event', 'concert', 'show', 'tour', 'ticket', 'venue', 'date'],
      matchmaking: ['match', 'friend', 'connect', 'meet', 'people', 'suggest', 'compatible'],
      profile: ['profile', 'account', 'settings', 'preferences', 'update'],
      help: ['help', 'how', 'what', 'where', 'when', 'why', 'explain', 'guide'],
      greeting: ['hi', 'hello', 'hey', 'greetings', 'sup'],
      goodbye: ['bye', 'goodbye', 'see you', 'later', 'thanks', 'thank you']
    };

    // Extract keywords from message
    const keywords = [];
    let detectedIntent = null;
    
    for (const [intent, terms] of Object.entries(intents)) {
      for (const term of terms) {
        if (lowerMessage.includes(term)) {
          keywords.push(term);
          if (!detectedIntent) detectedIntent = intent;
        }
      }
    }

    // Extract entities (artists, genres, locations, etc.)
    const entities = {
      artists: extractArtists(lowerMessage),
      genres: extractGenres(lowerMessage),
      locations: extractLocations(lowerMessage)
    };

    return {
      original: message,
      intent: detectedIntent || 'general',
      keywords,
      entities,
      sentiment: analyzeSentiment(message)
    };
  }

  // Extract artist names from message (basic pattern matching)
  function extractArtists(message) {
    // TODO: Enhance with NLP or API integration for better artist detection
    const commonArtists = ['tyler the creator', 'drake', 'kendrick', 'taylor swift', 'ariana grande'];
    return commonArtists.filter(artist => message.includes(artist));
  }

  // Extract music genres from message
  function extractGenres(message) {
    const genres = ['hip hop', 'rap', 'pop', 'rock', 'jazz', 'r&b', 'electronic', 'indie', 'country', 'classical'];
    return genres.filter(genre => message.includes(genre));
  }

  // Extract location mentions from message
  function extractLocations(message) {
    // TODO: Enhance with location parsing library
    const commonLocations = ['los angeles', 'new york', 'chicago', 'san francisco', 'miami'];
    return commonLocations.filter(location => message.includes(location));
  }

  // Basic sentiment analysis
  function analyzeSentiment(message) {
    const positiveWords = ['love', 'like', 'great', 'awesome', 'amazing', 'best', 'good', 'excited'];
    const negativeWords = ['hate', 'dislike', 'bad', 'terrible', 'worst', 'boring', 'sad'];
    
    const lower = message.toLowerCase();
    let score = 0;
    positiveWords.forEach(word => { if (lower.includes(word)) score++; });
    negativeWords.forEach(word => { if (lower.includes(word)) score--; });
    
    return score > 0 ? 'positive' : score < 0 ? 'negative' : 'neutral';
  }

  // Update conversation context based on parsed message
  function updateContext(parsedMessage) {
    chatState.context.currentTopic = parsedMessage.intent;
    chatState.context.conversationHistory.push(parsedMessage);
    
    // Keep only last 10 messages in history for context
    if (chatState.context.conversationHistory.length > 10) {
      chatState.context.conversationHistory.shift();
    }
  }

  // Generate bot response based on parsed message and context
  function generateResponse(parsedMessage) {
    const { intent, keywords, entities, sentiment } = parsedMessage;

    // Response templates - will be replaced with AI/backend integration
    switch (intent) {
      case 'greeting':
        return "Hello! How can I help you today? I can assist with music recommendations, event information, or matchmaking questions.";
      
      case 'music':
        if (entities.artists.length > 0) {
          return `I see you're interested in ${entities.artists[0]}. I can help you find similar artists or recommend playlists. Would you like me to suggest some music based on your taste?`;
        }
        if (entities.genres.length > 0) {
          return `Great! ${entities.genres[0]} is a fantastic genre. I can help you discover new artists in this style or find events related to it.`;
        }
        return "I'd love to help with music! You can ask me about artists, genres, recommendations, or connecting your Spotify account.";
      
      case 'events':
        if (entities.locations.length > 0) {
          return `I can help you find events in ${entities.locations[0]}. Check out the Events page for upcoming concerts and shows near you!`;
        }
        return "I can help you discover concerts and events! Would you like to see upcoming shows, search by artist, or check the concert map?";
      
      case 'matchmaking':
        return "Matchmaking helps you connect with people who share similar music tastes. I can help you understand how it works or adjust your matchmaking preferences in settings.";
      
      case 'profile':
        return "You can update your profile, music preferences, and settings. Would you like me to guide you to the profile or settings page?";
      
      case 'help':
        return "I'm here to help! I can assist with:\n• Music recommendations and artist information\n• Event and concert details\n• Matchmaking and connections\n• Profile and settings guidance\n\nWhat would you like to know?";
      
      case 'goodbye':
        return "Thanks for chatting! Feel free to come back anytime if you need help. Have a great day!";
      
      default:
        // Context-aware response based on conversation history
        const lastTopic = chatState.context.currentTopic;
        if (lastTopic) {
          return `I'm not sure I understand. Are you still asking about ${lastTopic}? Feel free to rephrase your question or ask for help!`;
        }
        return "I'm here to help! Try asking me about music, events, matchmaking, or your profile. What would you like to know?";
    }
  }
});
