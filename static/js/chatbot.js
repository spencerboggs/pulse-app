// Pulse assistant maps keywords to app routes and to curated events embedded at render time.
// Responses stay rule based while action rows deep link into matchmaking, settings, and event modals.

const chatState = {
  messages: [],
  context: {
    currentTopic: null,
    userPreferences: {},
    conversationHistory: []
  }
};

// Reads the JSON script tag emitted by Flask so term lists stay aligned with the events catalog.
function readPulseEventNav() {
  const el = document.getElementById('pulse-event-nav');
  if (!el) return [];
  try {
    const data = JSON.parse(el.textContent || '[]');
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const chatInput = document.getElementById('chatInput');
  const sendButton = document.getElementById('sendButton');
  const chatMessages = document.getElementById('chatMessages');
  const pulseNav = readPulseEventNav();

  if (!chatInput || !sendButton || !chatMessages) return;

  // Send via button or Enter without shift for a single line composer habit.
  sendButton.addEventListener('click', handleSendMessage);

  chatInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  });

  // Appends the user line, derives intent, optionally overrides copy when actions carry navigation.
  function handleSendMessage() {
    const messageText = chatInput.value.trim();
    if (!messageText) return;

    addMessageToChat(messageText, 'user');

    const parsedMessage = parseMessage(messageText);
    updateContext(parsedMessage);

    const actions = getSuggestedActions(parsedMessage);
    let response = generateResponse(parsedMessage);

    if (actions.length > 0) {
      const pulse = actions.filter((a) => (a.href || '').includes('/events?open='));
      if (pulse.length === 1) {
        response = `You can open ${pulse[0].eventTitle} from the catalog using the link below.`;
      } else if (pulse.length > 1) {
        response = 'These listings match what you said. Pick one for details and ticket links.';
      } else {
        response = 'Here are shortcuts that match what you asked.';
      }
    }

    setTimeout(() => {
      addMessageToChat(response, 'bot', actions);
    }, 500);

    chatInput.value = '';
  }

  // Builds message rows, attaches optional link buttons for bot replies, scrolls the transcript.
  function addMessageToChat(text, sender, actions) {
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

    if (sender === 'bot' && Array.isArray(actions) && actions.length > 0) {
      const actionsContainer = document.createElement('div');
      actionsContainer.className = 'message-actions';

      actions.forEach((action) => {
        const btn = document.createElement('a');
        btn.className = 'btn btn-primary btn-compact';
        btn.href = action.href;
        btn.textContent = action.label;
        if (action.target === '_blank') {
          btn.target = '_blank';
          btn.rel = 'noopener noreferrer';
        }
        actionsContainer.appendChild(btn);
      });

      bubble.appendChild(document.createElement('br'));
      bubble.appendChild(actionsContainer);
    }

    const time = document.createElement('div');
    time.className = 'message-time';
    time.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    content.appendChild(bubble);
    content.appendChild(time);
    messageDiv.appendChild(avatar);
    messageDiv.appendChild(content);

    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    chatState.messages.push({ text, sender, timestamp: new Date() });
  }

  // Static keyword lists map casual phrasing to stable in app paths, order defines tie breaking.
  const CTA_CONFIG = [
    {
      id: 'profile-customization',
      matchAny: ['profile', 'customize', 'customization', 'avatar', 'bio', 'about me', 'edit profile', 'preferences', 'settings', 'account'],
      label: 'Open Profile Settings',
      href: '/profile'
    },
    {
      id: 'settings',
      matchAny: ['settings', 'preferences', 'configuration'],
      label: 'Open App Settings',
      href: '/settings'
    },
    {
      id: 'friends',
      matchAny: ['friends', 'friend list', 'friendlist', 'connections', 'buddies'],
      label: 'View Messages',
      href: '/message'
    },
    {
      id: 'matchmaking',
      matchAny: ['match', 'matchmaking', 'connect', 'meet people', 'find friends'],
      label: 'Find Friends',
      href: '/matchmaking'
    },
    {
      id: 'events',
      matchAny: ['event', 'events', 'concert', 'concerts', 'shows', 'tour'],
      label: 'Browse Events',
      href: '/events'
    },
    {
      id: 'concert-map',
      matchAny: ['map', 'near me', 'nearby concerts', 'venues'],
      label: 'Open Concert Map',
      href: '/concert-map'
    }
  ];

  // Matches curated event terms against the lowercased message and returns deep links with open query params.
  function pulseEventActions(lower) {
    const out = [];
    const seen = new Set();
    for (const entry of pulseNav) {
      const terms = entry.match_terms || [];
      const hit = terms.some((t) => {
        const s = String(t).toLowerCase();
        if (s.length < 3) return false;
        return lower.includes(s);
      });
      if (hit && entry.id && !seen.has(entry.id)) {
        seen.add(entry.id);
        out.push({
          id: `pulse-event-${entry.id}`,
          label: `Open ${entry.title}`,
          href: `/events?open=${encodeURIComponent(entry.id)}`,
          eventTitle: entry.title
        });
      }
    }
    return out;
  }

  // Prefers specific event buttons, adds generic CTAs when no listing matched, caps count for layout balance.
  function getSuggestedActions(parsedMessage) {
    const lower = parsedMessage.original.toLowerCase();
    const pulseActions = pulseEventActions(lower);
    const actions = [...pulseActions];
    const seen = new Set(actions.map((a) => a.id));

    CTA_CONFIG.forEach((item) => {
      if (item.id === 'events' && pulseActions.length > 0) {
        return;
      }
      const hasMatch = item.matchAny.some((term) => lower.includes(term));
      if (hasMatch && !seen.has(item.id)) {
        actions.push({ id: item.id, label: item.label, href: item.href, target: item.target });
        seen.add(item.id);
      }
    });

    if (actions.length === 0) {
      switch (parsedMessage.intent) {
        case 'profile':
          actions.push({ id: 'fallback-profile', label: 'Open Profile Settings', href: '/profile' });
          break;
        case 'matchmaking':
          actions.push({ id: 'fallback-mm', label: 'Find Friends', href: '/matchmaking' });
          break;
        case 'events':
          actions.push({ id: 'fallback-events', label: 'Browse Events', href: '/events' });
          actions.push({ id: 'fallback-map', label: 'Open Concert Map', href: '/concert-map' });
          break;
        default:
          break;
      }
    }

    return actions.slice(0, 5);
  }

  // Scans intent vocabularies, records first hit as primary intent, collects light entity lists.
  function parseMessage(message) {
    const lowerMessage = message.toLowerCase();

    const intents = {
      music: ['music', 'song', 'artist', 'album', 'genre', 'listen', 'playlist', 'spotify'],
      events: ['event', 'concert', 'show', 'tour', 'ticket', 'venue', 'date'],
      matchmaking: ['match', 'friend', 'connect', 'meet', 'people', 'suggest', 'compatible'],
      profile: ['profile', 'account', 'settings', 'preferences', 'update'],
      help: ['help', 'how', 'what', 'where', 'when', 'why', 'explain', 'guide'],
      greeting: ['hi', 'hello', 'hey', 'greetings', 'sup'],
      goodbye: ['bye', 'goodbye', 'see you', 'later', 'thanks', 'thank you']
    };

    const keywords = [];
    let detectedIntent = null;

    for (const [intent, terms] of Object.entries(intents)) {
      const foundTerm = terms.find((term) => lowerMessage.includes(term));
      if (foundTerm) {
        keywords.push(foundTerm);
        if (!detectedIntent) detectedIntent = intent;
      }
    }

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

  // Small fixed artist list for highlighting names in free text during demos.
  function extractArtists(message) {
    const commonArtists = ['tyler the creator', 'drake', 'kendrick', 'taylor swift', 'ariana grande'];
    return commonArtists.filter((artist) => message.includes(artist));
  }

  // Genre tokens align with onboarding slugs where possible for consistent copy.
  function extractGenres(message) {
    const genres = ['hip hop', 'rap', 'pop', 'rock', 'jazz', 'r&b', 'electronic', 'indie', 'country', 'classical'];
    return genres.filter((genre) => message.includes(genre));
  }

  // Major city tokens support event and map oriented replies.
  function extractLocations(message) {
    const commonLocations = ['los angeles', 'new york', 'chicago', 'san francisco', 'miami'];
    return commonLocations.filter((location) => message.includes(location));
  }

  // Simple bag of word scoring for positive versus negative tone, used only for future extensions.
  function analyzeSentiment(message) {
    const positiveWords = ['love', 'like', 'great', 'awesome', 'amazing', 'best', 'good', 'excited'];
    const negativeWords = ['hate', 'dislike', 'bad', 'terrible', 'worst', 'boring', 'sad'];

    const lower = message.toLowerCase();
    const positiveCount = positiveWords.filter((word) => lower.includes(word)).length;
    const negativeCount = negativeWords.filter((word) => lower.includes(word)).length;
    const score = positiveCount - negativeCount;

    return score > 0 ? 'positive' : score < 0 ? 'negative' : 'neutral';
  }

  // Stores the latest intent and trims history so memory stays bounded in the browser.
  function updateContext(parsedMessage) {
    chatState.context.currentTopic = parsedMessage.intent;
    chatState.context.conversationHistory.push(parsedMessage);

    if (chatState.context.conversationHistory.length > 10) {
      chatState.context.conversationHistory.shift();
    }
  }

  // Template strings steer users toward real screens rather than inventing off platform facts.
  function generateResponse(parsedMessage) {
    const { intent, entities } = parsedMessage;

    switch (intent) {
      case 'greeting':
        return "Hello. Ask about events, matchmaking, settings, or say an artist or festival name for a direct link.";

      case 'music':
        if (entities.artists.length > 0) {
          return `You mentioned ${entities.artists[0]}. I can point you to related shows or help you tune matchmaking after you finish onboarding.`;
        }
        if (entities.genres.length > 0) {
          return `${entities.genres[0]} is a strong signal for recommendations. Ask about upcoming shows or open matchmaking to meet listeners with similar taste.`;
        }
        return "Tell me a genre or artist, or ask about linking Spotify from your profile flow when that is available.";

      case 'events':
        if (entities.locations.length > 0) {
          return `For gigs near ${entities.locations[0]}, open the concert map or browse events and filter by what matters to you.`;
        }
        return "Ask for a specific performance or festival by name, or say concerts to browse the full list.";

      case 'matchmaking':
        return "Matchmaking ranks people using your taste profile from onboarding and listening data. Open Find Friends when you are ready to send requests.";

      case 'profile':
        return "Profile and account preferences live under Profile and Settings. Say settings if you want notification toggles.";

      case 'help':
        return "I cover music and events, matchmaking, profile and settings, and quick links to main pages. Name an artist or event title for a direct button when it matches the catalog.";

      case 'goodbye':
        return "Goodbye. Come back any time for links into Pulse.";

      default: {
        const lastTopic = chatState.context.currentTopic;
        if (lastTopic) {
          return `I may have missed that. Are you still asking about ${lastTopic}? Rephrase or ask for help for a list of topics.`;
        }
        return "Ask about events, friends, settings, or name a show from the Pulse lineup.";
      }
    }
  }
});
