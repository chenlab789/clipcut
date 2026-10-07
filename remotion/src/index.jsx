import {registerRoot, Composition} from 'remotion';
import {Explainer} from './Explainer.jsx';

const Root = () => (
  <Composition
    id="Explainer"
    component={Explainer}
    fps={30}
    width={1080}
    height={1920}
    durationInFrames={30}
    defaultProps={{scenes: [], subs: [], total: 30}}
    calculateMetadata={({props}) => ({durationInFrames: Math.max(1, props.total || 30)})}
  />
);

registerRoot(Root);
