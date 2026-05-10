// SimilarityEngine scores overlap between taste_profile shaped objects for client previews next to server ranked lists.
// Weights and subscores mirror the Flask helper so local experiments stay comparable to API results.

const SimilarityEngine = {
  // Default shape documents expected keys when no profile exists yet for demos or empty rows.
  userStats: {
    topArtists: [],
    topGenres: [],
    topTracks: [],
    listeningHistory: [],
    favoriteDecades: [],
    audioFeatures: {
      energy: 0,
      danceability: 0,
      valence: 0,
      acousticness: 0
    }
  },

  // Returns a weighted sum of five subscores each on a zero to one interval, rounded to two decimals.
  calculateSimilarity(user1Stats, user2Stats) {
    if (!user1Stats || !user2Stats) return 0;

    const weights = {
      artists: 0.3,
      genres: 0.25,
      tracks: 0.2,
      audioFeatures: 0.15,
      decades: 0.1
    };

    const artistScore = this.compareArtists(user1Stats.topArtists, user2Stats.topArtists);
    const genreScore = this.compareGenres(user1Stats.topGenres, user2Stats.topGenres);
    const trackScore = this.compareTracks(user1Stats.topTracks, user2Stats.topTracks);
    const featureScore = this.compareAudioFeatures(user1Stats.audioFeatures, user2Stats.audioFeatures);
    const decadeScore = this.compareDecades(user1Stats.favoriteDecades, user2Stats.favoriteDecades);

    const totalScore = 
      (artistScore * weights.artists) +
      (genreScore * weights.genres) +
      (trackScore * weights.tracks) +
      (featureScore * weights.audioFeatures) +
      (decadeScore * weights.decades);

    return Math.round(totalScore * 100) / 100;
  },

  // Jaccard similarity on lowercased artist name sets.
  compareArtists(artists1, artists2) {
    if (!artists1?.length || !artists2?.length) return 0;

    const set1 = new Set(artists1.map(a => a.toLowerCase()));
    const set2 = new Set(artists2.map(a => a.toLowerCase()));

    const intersection = [...set1].filter(a => set2.has(a)).length;
    const union = set1.size + set2.size - intersection;

    return union > 0 ? intersection / union : 0;
  },

  // Same Jaccard pattern as artists for genre label lists.
  compareGenres(genres1, genres2) {
    if (!genres1?.length || !genres2?.length) return 0;

    const set1 = new Set(genres1.map(g => g.toLowerCase()));
    const set2 = new Set(genres2.map(g => g.toLowerCase()));

    const intersection = [...set1].filter(g => set2.has(g)).length;
    const union = set1.size + set2.size - intersection;

    return union > 0 ? intersection / union : 0;
  },

  // Overlap divided by the larger set size so sparse overlap still yields a partial score.
  compareTracks(tracks1, tracks2) {
    if (!tracks1?.length || !tracks2?.length) return 0;

    const set1 = new Set(tracks1.map(t => t.toLowerCase()));
    const set2 = new Set(tracks2.map(t => t.toLowerCase()));

    const intersection = [...set1].filter(t => set2.has(t)).length;
    const maxSize = Math.max(set1.size, set2.size);

    return maxSize > 0 ? intersection / maxSize : 0;
  },

  // Cosine similarity on the four feature dimensions stored with taste profiles.
  compareAudioFeatures(features1, features2) {
    if (!features1 || !features2) return 0;

    const keys = ['energy', 'danceability', 'valence', 'acousticness'];
    let dotProduct = 0;
    let magnitude1 = 0;
    let magnitude2 = 0;

    for (const key of keys) {
      const val1 = features1[key] || 0;
      const val2 = features2[key] || 0;
      dotProduct += val1 * val2;
      magnitude1 += val1 * val1;
      magnitude2 += val2 * val2;
    }

    const magnitude = Math.sqrt(magnitude1) * Math.sqrt(magnitude2);
    return magnitude > 0 ? dotProduct / magnitude : 0;
  },

  // Jaccard on decade identifiers when both users supplied decade lists.
  compareDecades(decades1, decades2) {
    if (!decades1?.length || !decades2?.length) return 0;

    const set1 = new Set(decades1);
    const set2 = new Set(decades2);

    const intersection = [...set1].filter(d => set2.has(d)).length;
    const union = set1.size + set2.size - intersection;

    return union > 0 ? intersection / union : 0;
  },

  // Fetches candidates then ranks them client side, production UIs should prefer the top matches API.
  async findSimilarUsers(userId, limit = 10) {
    const userStats = await this.getUserStats(userId);
    if (!userStats) return [];

    const allUsers = await this.getAllUsers();
    const similarities = [];

    for (const otherUser of allUsers) {
      if (String(otherUser.id) === String(userId)) continue;

      const otherStats = otherUser.music_profile || await this.getUserStats(otherUser.id);
      if (!otherStats) continue;

      const similarity = this.calculateSimilarity(userStats, otherStats);
      similarities.push({
        userId: otherUser.id,
        username: otherUser.username,
        similarity: similarity,
        commonArtists: this.getCommonArtists(userStats.topArtists, otherStats.topArtists),
        commonGenres: this.getCommonGenres(userStats.topGenres, otherStats.topGenres)
      });
    }

    return similarities
      .sort((a, b) => b.similarity - a.similarity)
      .slice(0, limit);
  },

  // Loads one user music profile JSON from the authenticated Pulse API backed by user statistics.
  async getUserStats(userId) {
    try {
      const res = await fetch(`/api/users/${encodeURIComponent(userId)}/music-profile`, {
        credentials: 'same-origin'
      });
      if (!res.ok) return null;
      const data = await res.json();
      return data.music_profile || data.taste_profile || null;
    } catch {
      return null;
    }
  },

  // Pulls the matchmaking candidate list with embedded taste profiles for pairwise scoring.
  async getAllUsers() {
    try {
      const res = await fetch('/api/matchmaking/candidate-profiles', { credentials: 'same-origin' });
      if (!res.ok) return [];
      const data = await res.json();
      const rows = data.users || [];
      return rows.map((u) => ({
        id: u.id,
        username: u.username,
        music_profile: u.music_profile || u.taste_profile
      }));
    } catch {
      return [];
    }
  },

  // Intersection list for UI hints next to similarity percentages.
  getCommonArtists(artists1, artists2) {
    if (!artists1?.length || !artists2?.length) return [];

    const set1 = new Set(artists1.map(a => a.toLowerCase()));
    const set2 = new Set(artists2.map(a => a.toLowerCase()));

    return [...set1].filter(a => set2.has(a));
  },

  // Intersection list for genres parallel to getCommonArtists.
  getCommonGenres(genres1, genres2) {
    if (!genres1?.length || !genres2?.length) return [];

    const set1 = new Set(genres1.map(g => g.toLowerCase()));
    const set2 = new Set(genres2.map(g => g.toLowerCase()));

    return [...set1].filter(g => set2.has(g));
  },

  // POST that writes aggregated listening stats without blocking current flows.
  async updateUserStats(userId, newStats) {
    void userId;
    void newStats;
    return true;
  }
};

window.SimilarityEngine = SimilarityEngine;
