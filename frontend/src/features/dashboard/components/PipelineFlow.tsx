import { ArrowRight } from 'lucide-react';
import { Card, CardTitle } from '../../../components/ui';
import { PIPELINE_STAGES } from '../constants/status';

export default function PipelineFlow() {
  return (
    <Card>
      <CardTitle className="mb-4">Pipeline Architecture</CardTitle>
      <div className="flex items-center gap-2 overflow-x-auto pb-2">
        {PIPELINE_STAGES.map((stage, index) => (
          <div key={stage} className="flex items-center gap-2">
            <span className="whitespace-nowrap rounded-lg bg-primary-50 px-4 py-2 text-sm font-medium text-primary-700">
              {stage}
            </span>
            {index < PIPELINE_STAGES.length - 1 ? <ArrowRight className="h-4 w-4 text-slate-400" /> : null}
          </div>
        ))}
      </div>
    </Card>
  );
}
