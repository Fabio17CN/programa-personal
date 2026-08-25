# Exercise Library 🏋️

> **1,112+ exercises** with animated GIFs, muscle targeting data, and step-by-step instructions

[![Exercises](https://img.shields.io/badge/Exercises-1,112+-blue.svg)](https://github.com/mohamedatef90/exercise-library)
[![Muscle Groups](https://img.shields.io/badge/Muscle%20Groups-19-green.svg)](https://github.com/mohamedatef90/exercise-library)
[![Equipment Types](https://img.shields.io/badge/Equipment-25%2B-orange.svg)](https://github.com/mohamedatef90/exercise-library)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 🎯 Features

- **🏋️ Comprehensive Database** — 1,112 exercises covering all major muscle groups
- **🎞️ Animated GIF Demonstrations** — Visual guide for proper form on every exercise
- **💪 Muscle Targeting Data** — Primary and secondary muscle groups identified
- **📊 Categorized by Body Parts** — Easy filtering by chest, back, legs, arms, core, etc.
- **🔧 Equipment-Based Filtering** — From body weight to barbells, dumbbells, and machines
- **📝 Step-by-Step Instructions** — Detailed breakdown for each exercise
- **⚡ JSON API** — Easy integration into fitness apps and websites
- **🌐 CDN-Ready GIFs** — Direct access via GitHub raw URLs

---

## 📂 Repository Structure

```
exercise-library/
├── exercises.json       # Complete exercise database (1.4MB)
├── gifs/               # 1,112 animated GIF files
│   ├── 2gPfomN.gif
│   ├── Hy9D21L.gif
│   └── ...
└── README.md
```

---

## 💪 Exercise Categories

### Muscle Groups (19 total)
- **Upper Body:** Chest, Back, Shoulders, Biceps, Triceps, Forearms
- **Core:** Abs, Obliques, Lower Back
- **Lower Body:** Quads, Hamstrings, Calves, Glutes, Hip Flexors
- **Full Body:** Compound movements targeting multiple muscle groups

### Body Parts
- Chest
- Back
- Shoulders
- Arms (Upper & Lower)
- Legs (Upper & Lower)
- Waist/Core
- Cardio

### Equipment Types (25+)
- Body Weight
- Barbell
- Dumbbell
- Kettlebell
- Cable Machine
- Resistance Bands
- Medicine Ball
- Stability Ball
- Bench
- Pull-up Bar
- And more...

---

## 🚀 Usage

### 1. Clone the Repository
```bash
git clone https://github.com/mohamedatef90/exercise-library.git
cd exercise-library
```

### 2. Access Exercise Data
```javascript
// Load all exercises
const exercises = require('./exercises.json');

// Filter by muscle group
const chestExercises = exercises.filter(ex => 
  ex.targetMuscles.includes('pectorals') || ex.targetMuscles.includes('chest')
);

// Filter by equipment
const bodyweightExercises = exercises.filter(ex =>
  ex.equipment.includes('body weight')
);

// Search by name
const pushups = exercises.filter(ex =>
  ex.name.toLowerCase().includes('push')
);
```

### 3. Display GIF Demonstrations
```javascript
// GIF URL pattern
const gifUrl = `https://raw.githubusercontent.com/mohamedatef90/exercise-library/main/gifs/${exercise.gif}`;

// Example: Show bench press GIF
const benchPress = exercises.find(ex => ex.name === 'barbell bench press');
const gifUrl = `https://raw.githubusercontent.com/mohamedatef90/exercise-library/main/gifs/${benchPress.gif}`;
```

---

## 📊 Data Structure

Each exercise in `exercises.json` follows this schema:

```json
{
  "id": "2gPfomN",
  "name": "3/4 sit-up",
  "gif": "2gPfomN.gif",
  "targetMuscles": ["abs"],
  "secondaryMuscles": ["hip flexors", "lower back"],
  "bodyParts": ["waist"],
  "equipment": ["body weight"],
  "instructions": [
    "Step:1 Lie flat on your back with your knees bent and feet flat on the ground.",
    "Step:2 Place your hands behind your head with your elbows pointing outwards.",
    "Step:3 Engaging your abs, slowly lift your upper body off the ground, curling forward until your torso is at a 45-degree angle.",
    "Step:4 Pause for a moment at the top, then slowly lower your upper body back down to the starting position.",
    "Step:5 Repeat for the desired number of repetitions."
  ]
}
```

### Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier for the exercise |
| `name` | string | Exercise name (e.g., "barbell bench press") |
| `gif` | string | Filename of the animated GIF demonstration |
| `targetMuscles` | array | Primary muscles worked |
| `secondaryMuscles` | array | Supporting muscles engaged |
| `bodyParts` | array | Body regions targeted |
| `equipment` | array | Required equipment |
| `instructions` | array | Step-by-step execution guide |

---

## 🔗 API Integration Examples

### React Component
```jsx
import React, { useState, useEffect } from 'react';
import exercisesData from './exercises.json';

function ExerciseLibrary() {
  const [exercises, setExercises] = useState([]);
  const [filter, setFilter] = useState('all');

  useEffect(() => {
    setExercises(exercisesData);
  }, []);

  const filterByMuscle = (muscle) => {
    if (muscle === 'all') {
      setExercises(exercisesData);
    } else {
      const filtered = exercisesData.filter(ex =>
        ex.targetMuscles.includes(muscle)
      );
      setExercises(filtered);
    }
  };

  return (
    <div>
      <h1>Exercise Library ({exercises.length} exercises)</h1>
      <button onClick={() => filterByMuscle('chest')}>Chest</button>
      <button onClick={() => filterByMuscle('back')}>Back</button>
      <button onClick={() => filterByMuscle('legs')}>Legs</button>
      
      <div className="exercise-grid">
        {exercises.map(ex => (
          <div key={ex.id} className="exercise-card">
            <h3>{ex.name}</h3>
            <img 
              src={`https://raw.githubusercontent.com/mohamedatef90/exercise-library/main/gifs/${ex.gif}`}
              alt={ex.name}
            />
            <p>Target: {ex.targetMuscles.join(', ')}</p>
            <p>Equipment: {ex.equipment.join(', ')}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export default ExerciseLibrary;
```

### Python Script
```python
import json

# Load exercises
with open('exercises.json', 'r', encoding='utf-8') as f:
    exercises = json.load(f)

# Find all chest exercises
chest_exercises = [
    ex for ex in exercises 
    if 'chest' in ex['targetMuscles'] or 'pectorals' in ex['targetMuscles']
]

print(f"Found {len(chest_exercises)} chest exercises")

# Get exercises that require no equipment
bodyweight_only = [
    ex for ex in exercises
    if ex['equipment'] == ['body weight']
]

print(f"Found {len(bodyweight_only)} bodyweight exercises")

# Display an exercise with instructions
exercise = exercises[0]
print(f"\n{exercise['name'].upper()}")
print(f"Target: {', '.join(exercise['targetMuscles'])}")
print(f"Equipment: {', '.join(exercise['equipment'])}")
print("\nInstructions:")
for step in exercise['instructions']:
    print(f"  {step}")
```

### REST API (Node.js/Express)
```javascript
const express = require('express');
const exercises = require('./exercises.json');
const app = express();

// Get all exercises
app.get('/api/exercises', (req, res) => {
  res.json(exercises);
});

// Get exercise by ID
app.get('/api/exercises/:id', (req, res) => {
  const exercise = exercises.find(ex => ex.id === req.params.id);
  if (exercise) {
    res.json(exercise);
  } else {
    res.status(404).json({ error: 'Exercise not found' });
  }
});

// Filter by muscle group
app.get('/api/exercises/muscle/:muscle', (req, res) => {
  const filtered = exercises.filter(ex =>
    ex.targetMuscles.includes(req.params.muscle.toLowerCase())
  );
  res.json(filtered);
});

// Filter by equipment
app.get('/api/exercises/equipment/:equipment', (req, res) => {
  const filtered = exercises.filter(ex =>
    ex.equipment.includes(req.params.equipment.toLowerCase())
  );
  res.json(filtered);
});

app.listen(3000, () => {
  console.log('Exercise API running on port 3000');
});
```

---

## 🛠️ Tech Stack

- **Data Format:** JSON (1.4MB total)
- **Media:** Animated GIF files (1,112 files)
- **Hosting:** GitHub repository + CDN via raw.githubusercontent.com
- **Integration:** Framework-agnostic (works with React, Vue, Angular, vanilla JS, Python, etc.)

---

## 🤝 Contributing

We welcome contributions! Here's how you can help improve the exercise library:

### Adding New Exercises

1. **Fork the repository**
2. **Add exercise data** to `exercises.json`:
   ```json
   {
     "id": "unique-id",
     "name": "Exercise Name",
     "gif": "filename.gif",
     "targetMuscles": ["primary muscle"],
     "secondaryMuscles": ["supporting muscles"],
     "bodyParts": ["body region"],
     "equipment": ["required equipment"],
     "instructions": [
       "Step:1 Description",
       "Step:2 Description",
       "Step:3 Description"
     ]
   }
   ```
3. **Add GIF file** to `gifs/` directory
4. **Submit a Pull Request**

### GIF Quality Standards

- **Format:** Animated GIF
- **Dimensions:** 400-600px width recommended
- **File Size:** Under 2MB per GIF
- **Loop:** Continuous loop showing full range of motion
- **Quality:** Clear demonstration of proper form
- **Background:** Clean, uncluttered background preferred

### Data Guidelines

- Use lowercase for muscle names and equipment
- Include all relevant target and secondary muscles
- Provide clear, step-by-step instructions
- Ensure proper exercise categorization
- Verify GIF filename matches the `gif` field

---

## 📝 Use Cases

### Fitness Apps
- Build workout generators
- Create custom training programs
- Exercise demonstration libraries
- Form guides and tutorials

### Educational Content
- Fitness blogs and articles
- YouTube workout videos
- Personal training resources
- Physical therapy guides

### Developer Projects
- Practice API integration
- Build portfolio projects
- Learn data manipulation
- Create fitness-related tools

---

## 📈 Database Statistics

- **Total Exercises:** 1,112
- **Muscle Groups:** 19
- **Equipment Types:** 25+
- **Body Parts:** 10+
- **Average Instructions per Exercise:** 4-6 steps
- **Total GIF Files:** 1,112
- **JSON File Size:** 1.4MB
- **Repository Size:** ~50MB (with all GIFs)

---

## 🌟 Roadmap

Future enhancements planned:

- [ ] **Video Demonstrations** — High-quality video alternatives to GIFs
- [ ] **Workout Builder** — Pre-built workout templates by goal (strength, hypertrophy, endurance)
- [ ] **Difficulty Levels** — Beginner, Intermediate, Advanced classifications
- [ ] **Calories Burned Estimates** — Estimated calorie expenditure per exercise
- [ ] **Alternative Exercises** — Suggest similar movements if equipment unavailable
- [ ] **Mobile App** — Native iOS/Android app for offline access
- [ ] **API Wrapper** — Official REST API with rate limiting and authentication
- [ ] **Multi-language Support** — Translated exercise names and instructions
- [ ] **3D Models** — Interactive 3D muscle visualization
- [ ] **Community Ratings** — User feedback on exercise effectiveness

---

## 🙏 Credits

- **Exercise Data:** Sourced from [ExerciseDB](https://rapidapi.com/justin-WFnsXH_t6/api/exercisedb) (open source)
- **GIF Demonstrations:** Community-contributed and curated
- **Maintained by:** [Mohamed Atef](https://github.com/mohamedatef90)

---

## 📄 License

This project is licensed under the **MIT License** — free to use, modify, and distribute.

See [LICENSE](LICENSE) file for details.

---

## 🔗 Links

- **Repository:** [github.com/mohamedatef90/exercise-library](https://github.com/mohamedatef90/exercise-library)
- **Issues:** [Report bugs or request features](https://github.com/mohamedatef90/exercise-library/issues)
- **Pull Requests:** [Contribute to the project](https://github.com/mohamedatef90/exercise-library/pulls)

---

## 💡 Quick Start Examples

### Get Random Exercise
```javascript
const exercises = require('./exercises.json');
const randomExercise = exercises[Math.floor(Math.random() * exercises.length)];
console.log(`Try this: ${randomExercise.name}`);
```

### Build a Workout
```javascript
const exercises = require('./exercises.json');

function generateWorkout(muscleGroup, count = 5) {
  const filtered = exercises.filter(ex =>
    ex.targetMuscles.includes(muscleGroup)
  );
  
  const workout = [];
  for (let i = 0; i < count; i++) {
    const randomIndex = Math.floor(Math.random() * filtered.length);
    workout.push(filtered[randomIndex]);
  }
  
  return workout;
}

const chestWorkout = generateWorkout('chest', 5);
console.log('Your Chest Workout:');
chestWorkout.forEach((ex, i) => {
  console.log(`${i + 1}. ${ex.name}`);
});
```

### Search Exercises
```javascript
const exercises = require('./exercises.json');

function searchExercises(query) {
  const lowerQuery = query.toLowerCase();
  return exercises.filter(ex =>
    ex.name.toLowerCase().includes(lowerQuery) ||
    ex.targetMuscles.some(m => m.includes(lowerQuery)) ||
    ex.equipment.some(e => e.includes(lowerQuery))
  );
}

const results = searchExercises('dumbbell');
console.log(`Found ${results.length} dumbbell exercises`);
```

---

**Ready to build something amazing?** 🚀 Clone the repo and start creating! 💪

Made with 💪 by the fitness & developer community
