import ReactDOM from 'react-dom/client';
import App from './App';
import Tracker from './Tracker';
import Overlay from './Overlay';
import VoicePilot from './VoicePilot';
import './styles.css';

const route = window.location.hash;
if (route === '#voice') {
  window.history.scrollRestoration = 'manual';
  document.title = 'H-Companion · Recette Odoo';
}
document.body.dataset.surface = route === '#tracker' ? 'tracker' : route === '#overlay' ? 'overlay' : route === '#voice' ? 'voice' : 'panel';
ReactDOM.createRoot(document.getElementById('root')!).render(
  route === '#tracker' ? <Tracker /> : route === '#overlay' ? <Overlay /> : route === '#voice' ? <VoicePilot /> : <App />,
);
