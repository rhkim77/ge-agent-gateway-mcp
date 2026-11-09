# frozen_string_literal: true

# ==============================================================================
# Step 3: Verify PSC Network Attachment, Cloud NAT, ACT & Egress Agent Gateway
# ==============================================================================
def step_3_agent_gateway_act_check(handles:, maximum_score:, resources:)
  ret_hash = {
    done: false,
    score: 0,
    message: 'error_message',
    student_message: 'error_message'
  }

  begin
    logging = handles['project_0.LoggingV2'] || handles[:LoggingV2]
    compute = handles['project_0.ComputeV1'] || handles[:ComputeV1]
    storage = handles['project_0.StorageV1'] || handles[:StorageV1]
    project_id = (resources['project_0']['project_id'] rescue nil) ||
                 (resources[:project_0][:project_id] rescue nil) ||
                 (logging.project rescue nil) ||
                 (storage.project rescue nil)

    verified = false

    if compute && project_id
      begin
        attachments = compute.list_network_attachments(project_id, 'us-central1')&.items || []
        verified = true if attachments.any? { |a| a.name.to_s.include?('cymbal-agw-psc-attachment') }
      rescue StandardError
        # Fallback to LoggingV2 / StorageV1 below
      end
    end

    if !verified && logging && project_id
      begin
        lab_start_time = Time.at(Time.now.to_i - 14_400).utc.iso8601
        custom_filter = [
          "timestamp>\"#{lab_start_time}\"",
          '(protoPayload.serviceName="networkservices.googleapis.com" OR protoPayload.serviceName="networkconnectivity.googleapis.com" OR protoPayload.serviceName="compute.googleapis.com")',
          '(protoPayload.methodName:"CreateAgentGateway" OR protoPayload.resourceName:"cymbal-aws-egress-gateway" OR protoPayload.resourceName:"cymbal-aws-egress-act" OR protoPayload.resourceName:"cymbal-agw-psc-attachment")'
        ].join(' AND ')

        request = Google::Apis::LoggingV2::ListLogEntriesRequest.new
        request.resource_names = ["projects/#{project_id}"]
        request.filter = custom_filter

        entries = logging.list_entry_log_entries(request)&.entries || []
        verified = true if entries.count.positive?
      rescue StandardError
        # Fallback to StorageV1 below
      end
    end

    if !verified && storage && project_id
      begin
        bucket_name = "#{project_id}-ge-agw-state"
        objects = storage.list_objects(bucket_name)&.items || []
        object_names = objects.map(&:name)
        verified = true if object_names.any? { |name| name.include?('step3_act_and_gateway_state.json') }
      rescue StandardError
        # Ignore fallback error
      end
    end

    if verified
      ret_hash = {
        done: true,
        score: maximum_score,
        message: 'success',
        student_message: 'success'
      }
    end
  rescue StandardError => e
    ret_hash[:message] = e.message
    ret_hash[:student_message] = 'error_message'
  end

  ret_hash
end
