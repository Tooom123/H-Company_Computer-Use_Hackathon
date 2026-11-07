import ReactDOM from 'react-dom/client';
import App from './App';
import Tracker from './Tracker';
import Overlay from './Overlay';
import './styles.css';

const route = window.location.hash;
document.body.dataset.surface = route === '#tracker' ? 'tracker' : route === '#overlay' ? 'overlay' : 'panel';
ReactDOM.createRoot(document.getElementById('root')!).render(
  route === '#tracker' ? <Tracker /> : route === '#overlay' ? <Overlay /> : <App />,
);
